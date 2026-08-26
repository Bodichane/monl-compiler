import os
import re
from typing import Any

from .errors import ValidationError
from .ir import CompilationIR
from .validation_pipeline import DEFAULT_VALIDATION_PIPELINE, ValidationPipeline

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


def candidats_asset(base_dir, dossier, chemin):
    """Les deux endroits où un asset déclaré peut vivre, dans l'ordre d'essai.

    Une valeur de seed vaut déjà 'assets/x.jpg' (c'est l'URL que le navigateur
    demandera) ; un logo est déclaré par son SEUL nom, le contrat préfixant
    ensuite par le dossier. Les deux formes sont donc légitimes."""
    chemin = chemin.strip()
    return [os.path.join(base_dir, chemin),
            os.path.join(base_dir, dossier, chemin)]


def resoudre_asset(base_dir, dossier, chemin):
    """Où vit réellement un asset déclaré, ou None.

    SOURCE UNIQUE de la résolution (point 84) : le validateur s'en sert pour
    REFUSER à la compilation, l'outil 'monl assets' pour RAPPORTER. Deux
    implémentations finiraient par diverger — l'outil dirait « présent » là où
    le compilateur dirait « absent »."""
    return next((c for c in candidats_asset(base_dir, dossier, chemin)
                 if os.path.isfile(c)), None)


class ASTValidationError(ValidationError):
    pass

class MonlAST:
    # Formats dont le détecteur d'octets et le service de lecture ont une
    # politique sûre. HTML et SVG ne sont pas acceptés : ils pourraient être
    # interprétés comme du code depuis l'origine de l'application.
    UPLOAD_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf",
    }

    def __init__(self, raw_json: dict[str, Any], base_dir: str | None = None):
        # AJOUT (brique 13, point 83) : 'base_dir' est le dossier du projet
        # (celui de la spec). Il n'est nécessaire qu'aux contrôles qui touchent
        # le DISQUE — vérifier qu'un asset déclaré existe vraiment. Les contrôles
        # de FORME (chemin absolu, remontée '..', URL distante) sont purs et
        # s'appliquent toujours : c'est le partage qui permet aux tests d'écrire
        # une spec en mémoire sans perdre les refus qui ne demandent pas de
        # fichier.
        self.base_dir = base_dir
        self.raw = raw_json
        self.app_name = raw_json.get("app")
        self.entities = {}
        # CORRECTIF (bêta 3, déterminisme) : la liste des acteurs était un
        # 'set', dont l'ordre d'itération dépend de PYTHONHASHSEED — deux
        # compilations de la même spec pouvaient produire un 'VALID_ACTORS'
        # différent dans app.py, ce qui contredisait la garantie « même
        # entrée, même sortie à l'octet près ». L'ordre de déclaration est
        # désormais conservé (dédoublonné).
        self.actors = list(dict.fromkeys(raw_json.get("actors", [])))
        # AJOUT (bêta 3) : acteurs ouverts à l'inscription libre (marqueur
        # 'selfRegister'). Les autres sont provisionnés hors ligne.
        self.self_register_actors = [
            a for a in dict.fromkeys(raw_json.get("self_register_actors", []))
            if a in self.actors
        ]
        self.relations = raw_json.get("relations", [])
        self.rules = raw_json.get("rules", [])
        self.workflows = raw_json.get("workflows", [])
        self.custom_logic = {c["name"]: c for c in raw_json.get("custom_logic", [])}
        self.ownership_rules = {}
        self.transitive_ownership = {}
        self.aggregated_fields = []
        self.access_party_rules = {}
        # AJOUT (brique 23, point 106) : rôles SUPERVISEURS par action régie
        # par 'accessibleBy'. Un rôle nommé ici (via une règle 'sharedBy' sur
        # la MÊME référence) transperce le contrôle par colonnes : il lit,
        # modifie ou supprime TOUS les enregistrements, quand les parties
        # restent enfermées dans les leurs.
        self.access_supervisors = {}
        self.ui_overrides_raw = raw_json.get("ui_overrides", [])
        self.landing_raw = raw_json.get("landing")
        self.capabilities_raw = raw_json.get("capabilities", [])
        self.seeds_raw = raw_json.get("seeds", [])
        self.assets_raw = raw_json.get("assets") or {}
        self.migrations_raw = raw_json.get("migrations", [])
        self.assets = {}
        self.public_actions = set()
        # Conditions de publication portées par `publicWhen` : elles doivent
        # être connues du générateur, pas seulement du frontend.
        self.public_conditions = {}
        # Unicités composites `oncePer` (ex. un compte ne vote qu'une fois par
        # entrée) — elles deviennent des index uniques multi-colonnes.
        self.once_per_rules = []
        self.upload_fields = []
        self.message_rules = []
        # BRIQUE B4 : options d'authentification déclarées sur capability auth.
        # Un dictionnaire vide est volontaire : il ne réveille aucune sortie
        # dans les specs historiques.
        self.auth_features = {}
        # BRIQUE 2a. None (et non EUR) tant que rien n'est déclaré : c'est la
        # règle du point 95 — une spec écrite avant cette brique doit compiler
        # à l'identique, et le défaut n'est appliqué qu'au moment d'encaisser.
        self.payment_currency = None
        self.payment_provider = None

        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate_and_audit(
            self, pipeline: ValidationPipeline = DEFAULT_VALIDATION_PIPELINE
    ) -> CompilationIR:
        """Exécute la validation de cohérence et l'analyse statique de sécurité."""
        print(f"🔬 Analyse statique et audit de sécurité pour '{self.app_name}'...")

        security_reports = pipeline.run(self)

        print("✅ Analyse de l'AST terminée.")
        return self.to_normalized_ast(security_reports)

    def _audit_self_registration(self):
        """Rapporte le périmètre d'inscription libre déclaré par la spec."""
        reports = []
        provisioned = [a for a in self.actors if a not in self.self_register_actors]
        if self.self_register_actors:
            print(f"🔓 Inscription libre : [{', '.join(self.self_register_actors)}]"
                  + (f" — provisionnés hors ligne : [{', '.join(provisioned)}]."
                     if provisioned else " (tous les rôles)."))
        elif self.actors:
            print("🔒 Aucun acteur 'selfRegister' : '/register' refusera toute inscription "
                  "(comptes à créer via 'python3 manage.py adduser').")
        if not self.self_register_actors:
            reports.append(
                "[SECURITY_NOTE] Aucun acteur n'est marqué 'selfRegister' : "
                "'POST /register' refusera toutes les inscriptions et les comptes "
                "devront être créés hors ligne (python3 manage.py adduser). "
                f"Pour ouvrir l'inscription d'un rôle : 'actor {self.actors[0]} selfRegister'."
                if self.actors else
                "[SECURITY_NOTE] Aucun acteur déclaré."
            )
        else:
            reports.append(
                "[SECURITY_NOTE] Inscription libre ouverte à "
                f"[{', '.join(self.self_register_actors)}]"
                + (f" ; rôles provisionnés hors ligne : [{', '.join(provisioned)}]."
                   if provisioned else " (tous les rôles déclarés).")
            )
        return reports

    def _verifier_forme_chemin_asset(self, valeur, ou, image=False):
        """Contrôles PURS sur un chemin d'asset — aucun accès disque, donc
        toujours actifs, y compris quand la spec est validée en mémoire.

        Un chemin absolu ou remontant sort du projet : servi tel quel par le
        navigateur il ne mènerait à rien, et écrit dans un seed il donne
        l'illusion d'un asset. Une URL distante, elle, est légitime — mais pas
        sous le type 'Image', dont toute la valeur est d'être vérifiable : le
        compilateur ne fait aucun appel réseau, il ne peut donc rien affirmer
        d'une URL. `String` reste là pour ce cas."""
        if not isinstance(valeur, str) or not valeur.strip():
            raise ASTValidationError(
                f"Structure : {ou} attend un chemin de fichier non vide.")
        chemin = valeur.strip()
        if image and "://" in chemin:
            raise ASTValidationError(
                f"Structure : {ou} vaut '{chemin}', une adresse distante, alors que le type "
                f"'Image' désigne un fichier LOCAL que le compilateur vérifie. monl ne fait "
                f"aucun appel réseau : il ne peut rien affirmer d'une URL. Déposer le fichier "
                f"dans le dossier d'assets, ou déclarer ce champ 'String' pour une adresse "
                f"distante (non vérifiée).")
        if chemin.startswith(("/", "\\")) or ":" in chemin.split("/")[0]:
            raise ASTValidationError(
                f"Structure : {ou} vaut '{chemin}', un chemin ABSOLU. Les assets sont relatifs "
                f"au projet, sans quoi le site ne serait servable que depuis cette machine.")
        if ".." in chemin.replace("\\", "/").split("/"):
            raise ASTValidationError(
                f"Structure : {ou} vaut '{chemin}', qui REMONTE hors du projet ('..'). Un asset "
                f"doit vivre dans le projet pour être déployé avec lui.")

    def _verifier_asset_present(self, valeur, ou):
        """Contrôle d'EXISTENCE — seulement quand on sait où est le projet.

        Sans 'base_dir' (spec validée en mémoire), on se TAIT plutôt que de
        deviner : un faux refus serait pire que l'absence de contrôle. Le
        silence est explicite, pas accidentel."""
        if not self.base_dir:
            return
        chemin = valeur.strip()
        dossier = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        if resoudre_asset(self.base_dir, dossier, chemin):
            return
        candidats = candidats_asset(self.base_dir, dossier, chemin)
        essayes = " ni ".join(os.path.relpath(c, self.base_dir) for c in candidats)
        raise ASTValidationError(
            f"Structure : {ou} désigne '{chemin}', qui n'existe pas ({essayes} introuvable). "
            f"Un asset déclaré mais absent donne une image cassée en ligne, que seul l'œil "
            f"repère -- c'est pourquoi la compilation échoue ici.")

    # Les quatre VALIDATION_TYPE de la grammaire, et ce qu'ils bornent selon le
    # type du champ. La longueur pour du texte, la valeur pour un nombre : c'est
    # la seule lecture naturelle de « min 3 » sur un nom et de « min 0 » sur un
    # prix, et elle doit être écrite quelque part plutôt que devinée.
    BORNES_TEXTE = ("String", "Text", "Email")
    BORNES_NOMBRE = ("Integer", "Float", "Money")
    # Longueur maximale de la colonne SQL correspondante (correctif bêta 3) :
    # un 'max' au-delà promettrait une donnée que la colonne ne peut pas tenir.
    LONGUEUR_COLONNE = {"String": 255, "Email": 320, "Text": 20000}

    # POINT 95 : formes reconnues pour l'identifiant de compte. 'libre' est le
    # comportement historique (n'importe quelle chaîne) et reste le défaut :
    # une spec qui ne dit rien compile exactement comme avant.
    FORMES_IDENTIFIANT = ("email", "phone", "libre")

    # BRIQUE B3 : ce sont les seuls types dont une égalité ou un tri a une
    # sémantique de donnée ordinaire. `Image` reste un chemin d'asset, et
    # `Upload` une référence de fichier : ni l'un ni l'autre ne devient un
    # critère d'énumération par accident.
    LIST_QUERY_TYPES = (
        "String", "Text", "Integer", "Float", "Boolean", "Date", "DateTime",
        "Email", "UUID", "Money",
    )
    LIST_QUERY_RESERVED = {"limit", "offset", "sort", "direction"}
    LIST_QUERY_SECRET_PARTS = (
        "password", "passwd", "secret", "token", "apikey", "api_key",
    )

    def _valider_identifiant_de_compte(self, capacites):
        """Formes acceptées par '/register', déclarées sur 'capability auth'.

        Retourne None quand rien n'est déclaré — et ce None compte : il vaut
        « aucune contrainte », pas « email par défaut ». Deviner ici
        verrouillerait tous les projets existants au premier recompilage."""
        formes, prefixe = None, None
        for capacite in capacites:
            if "phone_prefix" in capacite:
                valeur = capacite["phone_prefix"].strip()
                # Un indicatif est un '+' suivi de 1 à 4 chiffres : pas de
                # motif à importer pour si peu, et une dépendance de moins.
                if not (valeur.startswith("+") and valeur[1:].isdigit()
                        and 1 <= len(valeur) - 1 <= 4):
                    raise ASTValidationError(
                        f"Structure : 'phone_prefix' doit être un indicatif "
                        f"international — un '+' suivi de 1 à 4 chiffres "
                        f"(trouvé : {valeur!r}).")
                prefixe = valeur
            if "identifier" not in capacite:
                continue
            if capacite["name"] != "auth":
                raise ASTValidationError(
                    f"Structure : 'identifier' n'a de sens que sur "
                    f"'capability auth' (trouvé sur '{capacite['name']}') — "
                    "c'est l'inscription qu'il contraint.")
            demandees = list(dict.fromkeys(capacite["identifier"]))
            inconnues = [f for f in demandees if f not in self.FORMES_IDENTIFIANT]
            if inconnues:
                raise ASTValidationError(
                    f"Structure : forme(s) d'identifiant inconnue(s) : "
                    f"{', '.join(inconnues)}. Formes reconnues : "
                    f"{', '.join(self.FORMES_IDENTIFIANT)}.")
            # 'libre' accepte tout : le cumuler avec une forme stricte annule
            # cette dernière sans le dire. Un refus vaut mieux qu'une règle
            # écrite qui ne produit rien — c'est tout le point 85.
            if "libre" in demandees and len(demandees) > 1:
                raise ASTValidationError(
                    "Structure : 'identifier: libre' accepte déjà n'importe "
                    "quelle chaîne — le combiner avec "
                    f"{', '.join(f for f in demandees if f != 'libre')} "
                    "n'ajouterait aucune contrainte et laisserait croire le "
                    "contraire.")
            if formes is not None:
                raise ASTValidationError(
                    "Structure : 'identifier' déclaré deux fois sur "
                    "'capability auth' — une seule liste, sinon laquelle "
                    "s'applique ?")
            formes = demandees
        # Un indicatif sans forme 'phone' ne produirait RIEN : c'est ce que le
        # point 85 refuse. Le dire vaut mieux que le laisser croire appliqué.
        if prefixe and not (formes and "phone" in formes):
            raise ASTValidationError(
                "Structure : 'phone_prefix' n'a de sens qu'avec "
                "'identifier: … phone' — sans numéro à mettre sous forme "
                "canonique, il ne s'appliquerait à rien.")
        self.auth_phone_prefix = prefixe
        return formes

    def _valider_contraintes_de_champ(self):
        """POINT 85 : les quatre règles qui ne faisaient rien.

        `required`, `unique`, `min` et `max` — les plus anciennes du compilateur —
        étaient acceptées sans que RIEN ne les vérifie ni ne les applique. Deux
        constats, tous deux obtenus par exécution :

        * une référence fantôme passait en silence. `rule Product.nom required`
          au lieu de `name` : l'auteur croit tenir une contrainte, il n'en a
          aucune, et rien ne le dit ;
        * la sortie était IDENTIQUE À L'OCTET avec ou sans ces règles.
          `exemples/02_boutique.ml` déclare `rule Product.price min 0`, et le
          serveur acceptait `price: -99` — dans une boutique où le prix se
          multiplie en sous-total, se somme en total et part chez Stripe.

        Cette méthode ferme la première moitié (les références), et remplit
        `self.field_constraints` dont le générateur applique la seconde."""
        self.field_constraints = {}
        for rule in self.rules:
            type_regle = rule["type"]
            if type_regle not in ("required", "unique", "min", "max"):
                continue
            reference = rule["reference"]
            ou = f"rule {reference} {type_regle}"
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : '{ou}' doit référencer 'Entite.champ', reçu '{reference}'.")
            entite, champ = reference.split(".", 1)
            if entite not in self.entities:
                raise ASTValidationError(
                    f"Structure : '{ou}' référence l'entité '{entite}', qui n'existe pas. "
                    f"Entités déclarées : {', '.join(sorted(self.entities))}.")
            type_champ = self.entities[entite].get(champ)
            if type_champ is None:
                proches = [c for c in self.entities[entite] if c.lower() == champ.lower()]
                indice = f" Peut-être '{proches[0]}' ?" if proches else ""
                raise ASTValidationError(
                    f"Structure : '{ou}' référence le champ '{champ}', que l'entité "
                    f"'{entite}' ne déclare pas.{indice} Champs de {entite} : "
                    f"{', '.join(self.entities[entite])}. Une contrainte sur un champ "
                    f"inexistant ne s'applique à rien -- et laisse croire le contraire.")

            if type_champ == "Upload":
                raise ASTValidationError(
                    f"Structure : '{ou}' ne s'applique pas à '{reference}' de type Upload. "
                    "Un dépôt se contraint par 'upload max … types …', qui produit "
                    "les refus multipart réels du backend.")

            contraintes = self.field_constraints.setdefault((entite, champ), {})
            if type_regle in contraintes:
                raise ASTValidationError(
                    f"Structure : '{ou}' est déclaré deux fois sur le même champ.")
            if type_regle in ("required", "unique"):
                contraintes[type_regle] = True
                continue

            # 'min'/'max' : la grammaire n'accepte qu'un entier positif.
            try:
                borne = int(rule.get("value"))
            except (TypeError, ValueError):
                raise ASTValidationError(
                    f"Structure : '{ou}' attend un nombre entier "
                    f"(reçu '{rule.get('value')}').") from None
            if type_champ in self.BORNES_TEXTE:
                limite = self.LONGUEUR_COLONNE[type_champ]
                if borne > limite:
                    raise ASTValidationError(
                        f"Structure : '{ou} {borne}' dépasse la longueur de la colonne "
                        f"'{champ}' ({type_champ} = {limite} caractères). La contrainte "
                        f"promettrait une donnée que la base ne peut pas tenir.")
                contraintes[type_regle] = {"portee": "longueur", "valeur": borne}
            elif type_champ in self.BORNES_NOMBRE:
                contraintes[type_regle] = {"portee": "valeur", "valeur": borne}
            else:
                raise ASTValidationError(
                    f"Structure : '{ou}' porte sur '{champ}' de type '{type_champ}', "
                    f"que '{type_regle}' ne sait pas borner. Bornes de LONGUEUR sur "
                    f"{', '.join(self.BORNES_TEXTE)} ; bornes de VALEUR sur "
                    f"{', '.join(self.BORNES_NOMBRE)}.")

        for (entite, champ), contraintes in self.field_constraints.items():
            bas, haut = contraintes.get("min"), contraintes.get("max")
            if bas and haut and bas["valeur"] > haut["valeur"]:
                raise ASTValidationError(
                    f"Structure : '{entite}.{champ}' a min {bas['valeur']} et "
                    f"max {haut['valeur']} : aucune valeur ne satisfait les deux.")

    # Types sur lesquels une valeur de seed peut DÉSIGNER une ligne parente.
    # Un nombre est exclu : rapprocher deux flottants est déjà douteux, et un
    # prix ou un stock ne nomme rien — la désignation doit se lire.
    TYPES_DESIGNATION = ("String", "Text", "Email", "UUID")

    def _valider_parent_de_seed(self, entity, parent):
        """BRIQUE 21 (point 100) : `seed Enfant for Parent.champ "valeur"`.

        Sept refus, et le premier est celui qui porte la brique : la ligne
        parente doit être désignée SANS AMBIGUÏTÉ à la compilation. Un seed qui
        rattacherait « au hasard parmi deux » produirait une vitrine différente
        d'une compilation à l'autre, et personne ne le verrait avant de regarder
        l'écran."""
        cible = parent["entity"]
        champ = parent["field"]
        valeur = parent["value"]
        if cible not in self.entities:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à '{cible}', "
                f"qui n'est pas une entité déclarée.")
        # Même convention de relation que partout ailleurs (voir
        # _compute_fk_placements) : sans elle, aucune colonne ne porterait le
        # rattachement.
        lie = any(
            (rel["type"] in ("hasMany", "hasOne")
             and rel["source"] == cible and rel["target"] == entity)
            or (rel["type"] == "belongsTo"
                and rel["source"] == entity and rel["target"] == cible)
            for rel in self.relations
        )
        if not lie:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à '{cible}', mais "
                f"aucune relation ne les lie (ex. '{cible} hasMany {entity}') -- il "
                f"n'existe donc aucune colonne où écrire ce rattachement.")
        # POINT 99 : la colonne d'un parent ACTEUR porte un identifiant de
        # COMPTE, pas l'id d'une ligne. Un seed s'insère avant qu'aucun compte
        # n'existe : il n'y a rien à y désigner.
        if cible in self.actors:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à l'acteur "
                f"'{cible}'. Cette colonne-là porte un identifiant de COMPTE, "
                f"renseigné à la création depuis le jeton de l'appelant -- un jeu "
                f"de démonstration s'insère au démarrage, quand aucun compte "
                f"n'existe encore, et n'a donc personne à désigner.")
        if champ not in self.entities[cible]:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' désigne son parent par "
                f"'{cible}.{champ}', qui n'est pas un champ déclaré sur '{cible}'.")
        type_declare = self.entities[cible][champ]
        if type_declare not in self.TYPES_DESIGNATION:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' désigne son parent par "
                f"'{cible}.{champ}', de type {type_declare}. Désigner une ligne "
                f"demande un champ qui la NOMME : "
                f"{', '.join(self.TYPES_DESIGNATION)}.")
        # L'ordre compte pour de vrai : les données de démonstration sont
        # insérées table par table, dans l'ordre de DÉCLARATION des blocs. Un
        # parent semé après son enfant ne serait pas encore en base au moment de
        # rattacher, et la ligne serait écartée au démarrage. Refuser ici plutôt
        # que de réordonner en silence : la spec dirait une chose et le serveur
        # en ferait une autre.
        deja = [s for s in self.seeds if s["entity"] == cible]
        if not deja:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à un "
                f"'{cible}' qu'aucun bloc 'seed' n'a encore déclaré. Les données "
                f"de démonstration sont insérées dans l'ordre des blocs : "
                f"écrire 'seed {cible}' AVANT 'seed {entity}'.")
        correspondances = [ligne for bloc in deja for ligne in bloc["rows"]
                           if ligne.get(champ) == valeur]
        if not correspondances:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache au {cible} "
                f"'{champ}: \"{valeur}\"', qu'aucune ligne de 'seed {cible}' ne "
                f"porte. Une coquille ici donnerait une vitrine amputée sans que "
                f"rien ne le dise.")
        if len(correspondances) > 1:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache au {cible} "
                f"'{champ}: \"{valeur}\"', mais {len(correspondances)} lignes de "
                f"'seed {cible}' portent cette valeur -- rien ne dit à laquelle. "
                f"Désigner par un champ dont les valeurs sont distinctes.")

    # Jalons acceptés dans un gabarit de numéro. La séquence est le seul
    # obligatoire : sans elle, tous les enregistrements porteraient le même
    # numéro — une règle qui ne produit rien (point 85), doublée d'un index
    # unique qui refuserait la deuxième création.
    JALONS_DATE = ("YYYY", "MM", "DD")

    def _periode_du_gabarit(self, gabarit):
        """Sur quoi la séquence se REMET À ZÉRO : '' (jamais), 'YYYY',
        'YYYY-MM' ou 'YYYY-MM-DD'.

        Déduite des jalons de date présents, jamais déclarée à part : deux
        façons de dire la même chose finiraient par se contredire."""
        présents = [j for j in self.JALONS_DATE if "{" + j + "}" in gabarit]
        return "-".join(présents)

    def _valider_gabarit_de_numero(self, entity, field, gabarit):
        """Cinq refus sur la forme du gabarit lui-même."""
        jalons = re.findall(r"\{([^{}]*)\}", gabarit)
        # Une accolade orpheline ne serait pas vue par la recherche ci-dessus :
        # la compter séparément, sinon 'CMD-{YYYY' passerait pour du texte.
        if gabarit.count("{") != len(jalons) or gabarit.count("}") != len(jalons):
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' a une "
                f"accolade orpheline : {gabarit!r}.")
        sequences = [j for j in jalons if set(j) == {"N"}]
        inconnus = [j for j in jalons
                    if j not in self.JALONS_DATE and set(j) != {"N"}]
        if inconnus:
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' emploie "
                f"{', '.join(repr('{' + j + '}') for j in inconnus)}, qui ne veut rien "
                f"dire. Jalons acceptés : '{{YYYY}}', '{{MM}}', '{{DD}}', et une suite "
                f"de N pour la séquence ('{{NNNN}}' = quatre chiffres).")
        if not sequences:
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' n'a aucune "
                f"séquence ('{{NNNN}}') -- tous les enregistrements porteraient le MÊME "
                f"numéro, ce qui n'en est pas un.")
        if len(sequences) > 1:
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' contient "
                f"{len(sequences)} séquences -- rien ne dit laquelle s'incrémente.")
        # Une date incomplète fait se répéter la séquence : 'CMD-{MM}-{NNNN}'
        # redonne 'CMD-03-0001' tous les mois de mars. L'index unique
        # l'attraperait, mais un an plus tard et en production.
        # strict=False assumé : on apparie chaque jalon avec le SUIVANT, donc
        # les deux suites n'ont volontairement pas la même longueur.
        for précédent, suivant in zip(self.JALONS_DATE, self.JALONS_DATE[1:],
                                      strict=False):
            if "{" + suivant + "}" in gabarit and "{" + précédent + "}" not in gabarit:
                raise ASTValidationError(
                    f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' emploie "
                    f"'{{{suivant}}}' sans '{{{précédent}}}' -- la séquence se remettrait "
                    f"à zéro sans que le numéro dise de quelle période il s'agit, et "
                    f"deux enregistrements finiraient par porter le même.")

    def _valider_controle_dacces(self):
        """Le noyau du contrôle d'accès — frontière de sécurité (point 109).

        Rassemble, dans une passe dédiée du pipeline, TOUT ce qui décide QUI
        peut toucher QUOI : les règles 'ownedBy' (propriété
        directe), la résolution de la chaîne transitive jusqu'à un acteur
        (briques 11 et 24), les règles 'accessibleBy' (accès à plusieurs
        parties) et le rôle superviseur (brique 23). Peuple self.ownership_rules,
        self.transitive_ownership et self.access_supervisors, lus ensuite par le
        générateur via _transitive_chain / _owner_lookup_sql.

        N'utilise que self.* et constitue une frontière autonome du pipeline.
        """
        # AJOUT (post-v6, roadmap) : les règles 'ownedBy' restreignent une action
        # au seul enregistrement appartenant à l'acteur courant. Elles nécessitent
        # qu'une relation 'hasMany' existe entre l'entité "propriétaire" déclarée
        # et l'entité cible, pour fournir la colonne de clé étrangère qui stocke
        # le propriétaire (générée automatiquement en <source>_id).
        self.ownership_rules = {}
        for rule in self.rules:
            if rule["type"] == "ownedBy":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure : la règle 'ownedBy' doit référencer 'Entite.Action', reçu '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                owner_entity = rule["value"]

                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'ownedBy' cible l'entité '{entity}' qui n'existe pas.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure : action '{act_type}' invalide dans la règle 'ownedBy' sur '{entity}'.")
                # CORRECTIF (bêta 3) : 'Create' était accepté alors que le
                # générateur n'en fait rien — une règle de sécurité acceptée
                # puis silencieusement ignorée est pire que son absence, car
                # l'auteur de la spec croit la protection en place. À la
                # création, le propriétaire est l'appelant par construction :
                # la règle n'a rien à restreindre.
                if act_type == "Create":
                    raise ASTValidationError(
                        f"Structure : 'ownedBy' n'a pas de sens sur '{entity}.Create' — "
                        "à la création, le propriétaire est l'appelant par construction. "
                        "Utiliser 'ownedBy' sur Read, Update ou Delete.")

                # CORRECTIF (roadmap) : la vérification de la relation nécessaire
                # est désormais généralisée aux 3 types (hasMany, hasOne,
                # belongsTo), cohérente avec _compute_fk_placements() dans
                # generator.py — avant, seul 'hasMany' était reconnu ici, alors
                # que 'belongsTo'/'hasOne' fournissent aussi une colonne de
                # propriété valide selon leur propre convention de placement.
                has_matching_relation = any(
                    (rel["type"] in ("hasMany", "hasOne") and rel["source"] == owner_entity and rel["target"] == entity)
                    or (rel["type"] == "belongsTo" and rel["target"] == owner_entity and rel["source"] == entity)
                    for rel in self.relations
                )
                if not has_matching_relation:
                    raise ASTValidationError(
                        f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' référence le propriétaire "
                        f"'{owner_entity}', mais aucune relation compatible ('{owner_entity} hasMany {entity}', "
                        f"'{owner_entity} hasOne {entity}', ou '{entity} belongsTo {owner_entity}') n'est déclarée."
                    )

                # Le propriétaire nommé est soit un ACTEUR (propriété directe,
                # brique historique), soit une ENTITÉ (propriété TRANSITIVE,
                # brique 11 / point 81) -- ce second cas est résolu après cette
                # boucle, qui a besoin de connaître TOUTES les règles 'ownedBy'
                # pour remonter la chaîne jusqu'à un compte.
                self.ownership_rules[(entity, act_type)] = owner_entity

        # AJOUT (roadmap, écosystème de capacités -- brique 11, point 81) :
        # propriété TRANSITIVE. « Cette ligne de commande appartient à qui
        # possède sa commande » : le propriétaire nommé est une ENTITÉ, pas un
        # acteur, et la chaîne remonte jusqu'à un compte par la règle 'ownedBy'
        # de cet intermédiaire.
        #
        # Pourquoi cette résolution vit APRÈS la boucle : elle a besoin des
        # règles 'ownedBy' de l'intermédiaire, qui peuvent être déclarées plus
        # bas dans la spec que celle qui s'y réfère. Même motif que le
        # recoupement du point 79.
        #
        # Ce que le point 80 avait trouvé, et qui reste refusé ici : nommer une
        # entité qui ne remonte à AUCUN compte compilait en silence et
        # produisait du code incohérent — clé étrangère annoncée vers la table
        # des comptes, identifiant de l'appelant écrit à la place du
        # rattachement demandé, filtre de lecture comparant un id
        # d'enregistrement à un id de compte. Vérifié à l'exécution : une ligne
        # de commande se rattachait au compte de l'acheteur, jamais à la
        # commande nommée. La chaîne doit donc aboutir, sinon refus.
        self.transitive_ownership = {}
        proprietaires_par_entite = {}
        for (ent, _act), owner in self.ownership_rules.items():
            proprietaires_par_entite.setdefault(ent, set()).add(owner)

        for (entity, act_type), owner_entity in sorted(self.ownership_rules.items()):
            if owner_entity in self.actors:
                continue

            # AJOUT (brique 24, point 107) : la chaîne remontait jadis UN seul
            # intermédiaire ('{entity} -> via -> acteur'). Elle remonte
            # désormais toute la profondeur, maillon par maillon, jusqu'à un
            # ACTEUR. Chaque maillon doit être possédé par UN SEUL propriétaire
            # (sinon ambiguïté : quel chemin vérifier ?) et la marche ne doit
            # ni boucler ni aboutir dans le vide.
            maillon = owner_entity
            vus = set()
            chaine = []
            while maillon not in self.actors:
                if maillon in vus:
                    raise ASTValidationError(
                        f"Structure : la chaîne de propriété de '{entity}' boucle à '{maillon}' "
                        f"('{entity}' -> {' -> '.join(chaine)} ...) -- le serveur ne peut la "
                        f"résoudre. Couper le cycle."
                    )
                vus.add(maillon)
                chaine.append(maillon)
                parents = proprietaires_par_entite.get(maillon, set())
                if not parents:
                    raise ASTValidationError(
                        f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' désigne "
                        f"'{owner_entity}' comme propriétaire, mais la chaîne '{entity}' -> "
                        f"{' -> '.join(chaine)} ne remonte à AUCUN acteur -- le serveur ne peut "
                        f"vérifier À QUI appartient un '{entity}'. Ajouter une règle "
                        f"'<dernier maillon>.Read ownedBy <Acteur>', ou rattacher '{entity}' "
                        f"directement à un acteur."
                    )
                if len(parents) > 1:
                    raise ASTValidationError(
                        f"Structure : la chaîne de propriété de '{entity}' est ambiguë à "
                        f"'{maillon}' : celui-ci est possédé par plusieurs entités différentes "
                        f"({', '.join(sorted(parents))}) -- le serveur ne saurait pas laquelle "
                        f"vérifier. N'en désigner qu'une seule sur '{maillon}'."
                    )
                maillon = next(iter(parents))
            acteur = maillon
            # Mélanger propriété directe et transitive sur la MÊME entité
            # rendrait sa clé étrangère à la fois peuplée depuis le jeton (pour
            # l'une des règles) et fournie par le client (pour l'autre) : deux
            # traitements contradictoires sur une seule colonne.
            autres = proprietaires_par_entite.get(entity, set()) - {owner_entity}
            if autres:
                raise ASTValidationError(
                    f"Structure : '{entity}' est possédé à travers '{owner_entity}' (propriété "
                    f"transitive) mais déclare aussi '{', '.join(sorted(autres))}' comme propriétaire "
                    f"-- sa clé étrangère de propriété serait à la fois fournie par le client et "
                    f"déduite du jeton. Ne désigner qu'un seul propriétaire pour '{entity}'."
                )
            self.transitive_ownership[entity] = {"chain": chaine, "actor": acteur}

        # AJOUT (roadmap, écosystème de capacités -- brique "accès à deux
        # parties") : les règles 'accessibleBy' restreignent une action aux
        # seuls enregistrements dont l'une des colonnes listées contient
        # l'identifiant de l'appelant. Cas d'usage canonique : messagerie
        # privée (expéditeur via la colonne de relation auto-peuplée,
        # destinataire via un champ Integer déclaré). Chaque colonne doit
        # être soit un champ Integer déclaré de l'entité, soit la colonne de
        # clé étrangère dérivée d'une relation entrante (ex. 'user_id').
        self.access_party_rules = {}
        for rule in self.rules:
            if rule["type"] != "accessibleBy":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'accessibleBy' doit référencer 'Entite.Action', reçu '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            columns = rule["value"]

            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'accessibleBy' cible l'entité '{entity}' qui n'existe pas.")
            if act_type not in ("Read", "Update", "Delete"):
                raise ASTValidationError(
                    f"Structure : action '{act_type}' invalide dans la règle 'accessibleBy' sur '{entity}' "
                    f"(seules Read/Update/Delete portent sur un enregistrement existant dont on peut vérifier les parties)."
                )
            if len(set(columns)) < 2:
                raise ASTValidationError(
                    f"Structure : la règle 'accessibleBy' sur '{entity}.{act_type}' doit lister au moins deux "
                    f"colonnes DISTINCTES — avec une seule partie, utiliser 'ownedBy'."
                )

            # Colonnes de clé étrangère qu'une relation entrante fournit à
            # cette entité (même convention que _compute_fk_placements dans
            # generator.py : '<source>_id').
            relation_fk_columns = set()
            for rel in self.relations:
                if rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity:
                    relation_fk_columns.add(f"{rel['source'].lower()}_id")
                elif rel["type"] == "belongsTo" and rel["source"] == entity:
                    relation_fk_columns.add(f"{rel['target'].lower()}_id")

            for col in columns:
                declared_type = self.entities[entity].get(col)
                if col in relation_fk_columns:
                    continue
                if declared_type is None:
                    raise ASTValidationError(
                        f"Structure : la règle 'accessibleBy' sur '{entity}.{act_type}' référence la colonne "
                        f"'{col}', qui n'est ni un champ déclaré de '{entity}', ni une colonne de relation "
                        f"entrante ({', '.join(sorted(relation_fk_columns)) or 'aucune relation entrante'})."
                    )
                if declared_type != "Integer":
                    raise ASTValidationError(
                        f"Structure : la règle 'accessibleBy' sur '{entity}.{act_type}' exige que '{col}' soit "
                        f"de type Integer (identifiant d'utilisateur), reçu '{declared_type}'."
                    )

            if (entity, act_type) in self.ownership_rules:
                raise ASTValidationError(
                    f"Conflit : '{entity}.{act_type}' porte à la fois 'ownedBy' et 'accessibleBy' — "
                    f"choisir l'un des deux ('accessibleBy' généralise 'ownedBy' à plusieurs parties)."
                )

            self.access_party_rules[(entity, act_type)] = list(columns)

            # AJOUT (brique 23, point 106) : un rôle SUPERVISEUR peut
            # transpercer ce contrôle par colonnes. Syntaxe : une règle
            # 'sharedBy' portant la MÊME référence — 'rule Message.Delete
            # sharedBy Moderator' posé à côté de 'rule Message.Delete
            # accessibleBy member_id, recipient_id'. Le rôle ainsi nommé
            # voit/supprime/modifie tous les enregistrements ; les parties,
            # elles, restent confinées aux leurs. C'est pour 'accessibleBy' le
            # pendant exact du superviseur déjà acquis pour 'ownedBy' au
            # point 88 ('rule X.Update sharedBy Proprietaire, Patron'). Les
            # rôles nommés doivent être des acteurs déclarés.
            superviseurs = self._superviseurs_declares(entity, act_type)
            if superviseurs:
                self.access_supervisors[(entity, act_type)] = superviseurs

    def _valider_champs_uploades(self):
        """Valide la déclaration complète d'un dépôt client.

        ``Image`` reste un chemin d'asset contrôlé à la compilation. Un
        ``Upload`` n'est accepté que s'il est relié à une règle complète, à
        une route d'écriture et de lecture, et à une ACL privée par
        enregistrement.
        """
        for custom in self.custom_logic.values():
            for input_ in custom.get("input", []):
                reference = input_.get("reference")
                input_type = input_.get("type")
                referenced_type = None
                if reference and "." in reference:
                    ref_entity, ref_field = reference.split(".", 1)
                    referenced_type = self.entities.get(ref_entity, {}).get(ref_field)
                if input_type == "Upload" or referenced_type == "Upload":
                    raise ASTValidationError(
                        f"Structure : le bloc custom '{custom['name']}' ne peut pas "
                        "prendre un Upload en entrée. Les octets passent uniquement "
                        "par la route multipart de l'entité, jamais par la sandbox.")
        regles = {}
        for rule in self.rules:
            if rule.get("type") != "upload":
                continue
            reference = rule.get("reference", "")
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' doit référencer 'Entite.champ', "
                    f"reçu '{reference}'.")
            entity, field = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' cible l'entité '{entity}', "
                    "qui n'existe pas.")
            declared = self.entities[entity].get(field)
            if declared is None:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' cible le champ '{reference}', "
                    "qui n'est pas déclaré.")
            if declared != "Upload":
                raise ASTValidationError(
                    f"Structure : la règle 'upload' cible '{reference}' de type "
                    f"'{declared}'. Seul le type Upload accepte un dépôt client ; "
                    "Image reste un asset fourni à la compilation.")
            if reference in regles:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'upload' déclarent '{reference}'.")
            maximum = rule.get("max_bytes")
            if not isinstance(maximum, int) or maximum <= 0:
                raise ASTValidationError(
                    f"Structure : la taille maximale de '{reference}' doit être un "
                    f"entier strictement positif (reçu {maximum!r}).")
            accepted = list(rule.get("accepted_types") or [])
            if not accepted:
                raise ASTValidationError(
                    f"Structure : la règle 'upload' de '{reference}' doit déclarer "
                    "au moins un type MIME autorisé.")
            if len(set(accepted)) != len(accepted):
                raise ASTValidationError(
                    f"Structure : la règle 'upload' de '{reference}' répète un type "
                    "MIME ; chaque type doit être déclaré une seule fois.")
            inconnus = [mime for mime in accepted if mime not in self.UPLOAD_TYPES]
            if inconnus:
                raise ASTValidationError(
                    f"Structure : type(s) MIME non autorisé(s) pour '{reference}' : "
                    f"{', '.join(inconnus)}. Formats sûrs reconnus : "
                    f"{', '.join(sorted(self.UPLOAD_TYPES))}. HTML et SVG exécutables "
                    "sont refusés par conception.")
            regles[reference] = {
                "entity": entity, "field": field, "max_bytes": maximum,
                "accepted_types": accepted,
            }

        for entity, fields in self.entities.items():
            for field, declared in fields.items():
                reference = f"{entity}.{field}"
                if declared == "Upload" and reference not in regles:
                    raise ASTValidationError(
                        f"Structure : '{reference}: Upload' n'a aucune règle de dépôt. "
                        f"Déclarer 'rule {reference} upload max N types \"…\"' : "
                        "le type seul ne produirait ni limite ni route.")

        for reference, rule in regles.items():
            entity = rule["entity"]
            has_actions = {
                action["type"]
                for workflow in self.workflows
                for action in workflow["actions"]
                if action["type"] in ("Read", "Update")
                and action["target"].split(".", 1)[0] == entity
            }
            missing = {"Read", "Update"} - has_actions
            if missing:
                raise ASTValidationError(
                    f"Structure : '{reference}' nécessite des workflows Read et Update "
                    f"sur '{entity}' pour produire les routes de lecture/dépôt ; "
                    f"il manque {', '.join(sorted(missing))}.")
            for action in ("Read", "Update"):
                if (entity, action) in self.public_actions or (
                        action == "Read" and (entity, "Read") in self.public_conditions):
                    raise ASTValidationError(
                        f"Sécurité : le fichier '{reference}' est privé par défaut ; "
                        f"'{entity}.{action}' ne peut pas être public. Le contenu d'un "
                        "Upload ne doit jamais être lisible sans l'ACL de la ligne.")
                if (entity, action) not in self.ownership_rules and (
                        entity, action) not in self.access_party_rules:
                    raise ASTValidationError(
                        f"Sécurité : '{entity}.{action}' doit porter 'ownedBy' ou "
                        "'accessibleBy' pour qu'un fichier Upload ne soit pas lisible "
                        "par simple connaissance de son chemin.")
        self.upload_fields = [
            regles[f"{entity}.{field}"]
            for entity, fields in self.entities.items()
            for field, declared in fields.items()
            if declared == "Upload"
        ]

    def _superviseurs_declares(self, entity, act_type):
        """Les rôles nommés par un 'sharedBy' portant la référence exacte.

        Source UNIQUE du superviseur, partagée par 'accessibleBy' (brique 23,
        point 106) et par 'publicWhen' (point 116). Deux résolutions
        parallèles finiraient par diverger sur la validation des rôles — et
        c'est justement cette validation qui empêche qu'une faute de frappe
        désactive silencieusement la supervision (même leçon qu'au point 112).
        """
        ref = f"{entity}.{act_type}"
        superviseurs = []
        for r in self.rules:
            if r["type"] == "sharedBy" and r["reference"] == ref:
                for role in r["value"]:
                    if role not in self.actors:
                        raise ASTValidationError(
                            f"Structure : le rôle superviseur '{role}' de la règle "
                            f"'sharedBy' sur '{ref}' n'est pas un acteur déclaré."
                        )
                    if role not in superviseurs:
                        superviseurs.append(role)
        return superviseurs

    def _valider_regle_public(self):
        """La règle 'public' — une action qui n'exige plus d'authentification
        (point 111). N'utilise que self.rules, self.entities,
        self.public_actions."""
        # AJOUT (roadmap, cas d'usage portfolio) : validation des règles
        # 'public' — une action ainsi marquée n'exige plus d'authentification
        # sur la route générée (ex. lecture d'un portfolio sans compte,
        # envoi d'un message de contact sans compte).
        for rule in self.rules:
            if rule["type"] == "public":
                if "." not in rule["reference"]:
                    raise ASTValidationError(
                        f"Structure : la règle 'public' doit référencer 'Entite.Action', reçu '{rule['reference']}'."
                    )
                entity, act_type = rule["reference"].split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(f"Structure : la règle 'public' cible l'entité '{entity}' qui n'existe pas.")
                if act_type not in ("Create", "Read", "Update", "Delete"):
                    raise ASTValidationError(f"Structure : action '{act_type}' invalide dans la règle 'public' sur '{entity}'.")
                self.public_actions.add((entity, act_type))
            elif rule["type"] == "publicWhen":
                reference = rule["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' doit référencer 'Entite.Read', reçu '{reference}'."
                    )
                entity, act_type = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' cible l'entité '{entity}' qui n'existe pas."
                    )
                if act_type != "Read":
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' ne vaut que sur 'Read' (reçu '{reference}')."
                    )
                field = rule.get("field")
                if field not in self.entities[entity]:
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' cible le champ '{field}' qui n'existe pas sur '{entity}'."
                    )
                if self.entities[entity][field] not in ("String", "Text", "Email", "UUID"):
                    raise ASTValidationError(
                        f"Structure : 'publicWhen' exige un champ texte, reçu '{entity}.{field}' "
                        f"de type '{self.entities[entity][field]}'."
                    )
                if (entity, act_type) in self.public_actions:
                    raise ASTValidationError(
                        f"Structure : '{reference}' est à la fois 'public' et 'publicWhen' — "
                        "une seule politique de visibilité est autorisée."
                    )
                if (entity, act_type) in self.public_conditions:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'publicWhen' sur '{reference}' — "
                        "la condition serait ambiguë."
                    )
                self.public_actions.add((entity, act_type))
                self.public_conditions[(entity, act_type)] = {
                    "field": field, "value": rule.get("value", "")
                }
                # POINT 116 : un 'sharedBy' sur la MÊME référence nomme les
                # rôles qui transpercent la condition — même mot-clé et même
                # sens que le superviseur d'accessibleBy (brique 23). Sans
                # lui, masquer un contenu le retirait AUSSI au modérateur qui
                # venait de le masquer : il ne pouvait plus ni le relire ni
                # revenir en arrière.
                superviseurs = self._superviseurs_declares(entity, act_type)
                if superviseurs:
                    self.access_supervisors[(entity, act_type)] = superviseurs

    def _valider_regles_once_per(self):
        """Valide l'unicité métier d'une action par compte et par cibles.

        `oncePer Member, Entry` désigne les deux relations qui composent la
        clé unique de Vote. Le parent acteur est alimenté depuis le JWT ; les
        autres parents restent fournis comme clés étrangères normales.
        """
        self.once_per_rules = []
        for rule in self.rules:
            if rule["type"] != "oncePer":
                continue
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : 'oncePer' doit référencer 'Entite.Create', reçu '{reference}'."
                )
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'oncePer' cible l'entité '{entity}' qui n'existe pas."
                )
            if action != "Create":
                raise ASTValidationError(
                    f"Structure : 'oncePer' ne vaut que sur 'Create' (reçu '{reference}')."
                )
            parents = list(rule.get("parents") or [])
            if len(parents) < 2 or len(set(parents)) != len(parents):
                raise ASTValidationError(
                    f"Structure : 'oncePer' sur '{reference}' exige au moins deux parents distincts."
                )
            for parent in parents:
                if parent not in self.entities and parent not in self.actors:
                    raise ASTValidationError(
                        f"Structure : 'oncePer' référence le parent '{parent}', qui n'existe pas."
                    )
                relie = any(
                    (rel["type"] in ("hasMany", "hasOne")
                     and rel["source"] == parent and rel["target"] == entity)
                    or (rel["type"] == "belongsTo"
                        and rel["target"] == parent and rel["source"] == entity)
                    for rel in self.relations
                )
                if not relie:
                    raise ASTValidationError(
                        f"Structure : 'oncePer' exige une relation entre '{parent}' et '{entity}'."
                    )
            if not any(parent in self.actors for parent in parents):
                raise ASTValidationError(
                    f"Structure : 'oncePer' sur '{reference}' doit inclure un parent acteur "
                    "pour identifier le compte courant."
                )
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{reference}' est public, donc aucun compte ne peut porter "
                    "l'unicité 'oncePer'."
                )
            self.once_per_rules.append({"trigger_entity": entity, "parents": parents})

    def _valider_requires_own_et_payable(self):
        """'requiresOwn' (brique 17) et 'payable' (brique paiement) — les
        prérequis de création qui protègent qui peut agir et qui peut encaisser
        (point 111). Extraits ensemble parce qu'ils partagent les prérequis de
        propriété, de visibilité publique et de champs masqués."""
        # AJOUT (roadmap, écosystème de capacités -- brique 17, point 90) :
        # validation de 'requiresOwn'. L'appelant doit DÉJÀ posséder un
        # enregistrement de l'entité nommée pour pouvoir créer celui-ci.
        #
        # Le constat qui l'a fait naître, sur une boutique réelle : deux
        # commandes portaient un compte SANS aucune fiche client. Rien
        # n'obligeait à en créer une avant de commander, et le registre des
        # comptes n'est exposé par aucune route — l'administrateur voyait donc
        # une commande qu'il ne pouvait attribuer à personne. Pour une boutique,
        # ce n'est pas un défaut d'affichage : c'est une commande inexpédiable.
        self.required_profiles = {}
        for rule in self.rules:
            if rule["type"] != "requiresOwn":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'requiresOwn' doit référencer 'Entite.Action', "
                    f"reçu '{rule['reference']}'."
                )
            entity, act_type = rule["reference"].split(".", 1)
            requise = rule["value"]
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'requiresOwn' cible l'entité '{entity}' qui n'existe pas."
                )
            # Seule la création peut l'exiger : c'est le moment où
            # l'enregistrement naît sans propriétaire nommé. Sur Read/Update/
            # Delete, l'enregistrement existe déjà — exiger une fiche a
            # posteriori rendrait inaccessibles des données qu'on possède.
            if act_type != "Create":
                raise ASTValidationError(
                    f"Structure : 'requiresOwn' ne vaut que sur '{entity}.Create' "
                    f"(reçu '{entity}.{act_type}') -- sur une action de lecture ou de "
                    f"modification, l'enregistrement existe déjà et sa fiche ne peut "
                    f"plus rien empêcher."
                )
            if requise not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'requiresOwn' sur '{entity}.Create' exige un "
                    f"'{requise}', qui n'est pas une entité déclarée."
                )
            if requise == entity:
                raise ASTValidationError(
                    f"Structure : '{entity}.Create requiresOwn {entity}' -- une entité ne "
                    f"peut pas exiger d'elle-même : le premier enregistrement ne pourrait "
                    f"jamais être créé."
                )
            # L'entité exigée doit être possédée DIRECTEMENT par un acteur :
            # « en posséder un » n'a de sens que si la propriété se déduit du
            # jeton. Une entité possédée transitivement (brique 11) ne dit pas
            # à quel COMPTE elle appartient sans jointure, et une entité sans
            # propriétaire du tout n'appartient à personne.
            proprietaires = {v for (ent, _act), v in self.ownership_rules.items()
                             if ent == requise}
            if not (proprietaires & set(self.actors)):
                raise ASTValidationError(
                    f"Structure : '{entity}.Create requiresOwn {requise}', mais "
                    f"'{requise}' n'est possédé par aucun acteur -- « en posséder un » "
                    f"ne veut alors rien dire. Ajouter une règle "
                    f"'rule {requise}.Read ownedBy <Acteur>'."
                )
            # Une création publique n'a aucune identité : impossible de chercher
            # « sa » fiche. Même refus que 'generated' et 'payable', même raison.
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{entity}.Create' est 'public' et exige pourtant un "
                    f"'{requise}' possédé -- incompatible : sans appelant identifié, "
                    f"aucune fiche ne peut être cherchée."
                )
            if entity in self.required_profiles:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'requiresOwn' déclarées pour "
                    f"'{entity}.Create' -- une seule autorisée."
                )
            self.required_profiles[entity] = requise

        # AJOUT (roadmap, brique paiement -- point 74) : validation de
        # 'payable'. La règle nomme le champ qui porte le MONTANT ; l'entité
        # qui le contient est celle qu'on encaisse. Les refus ci-dessous sont
        # le cœur de la brique : un paiement mal déclaré doit échouer à la
        # compilation, jamais au moment d'encaisser.
        self.payable_fields = []
        for rule in self.rules:
            if rule["type"] != "payable":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'payable' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'payable' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'payable' cible le champ '{entity}.{field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {field_type or 'champ inexistant'}) -- "
                    f"on n'encaisse pas du texte."
                )
            # Un montant masqué serait invérifiable par le client qui paie :
            # il ne pourrait pas confronter ce qu'on lui demande à ce qu'il a
            # commandé.
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'payable' -- incompatible : "
                    f"un montant qu'on ne peut pas lire ne peut pas être vérifié par celui qui le règle."
                )
            if any(p["entity"] == entity for p in self.payable_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}' porte plusieurs champs 'payable' -- un seul montant par entité, "
                    f"sinon rien ne dit lequel encaisser."
                )
            # Encaisser exige de savoir QUI paie : une création publique n'a
            # aucune identité à rattacher au règlement, ni personne à qui
            # rendre l'argent.
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable', mais '{entity}.Create' est 'public' -- "
                    f"incompatible : un paiement exige un appelant identifié."
                )
            # CORRECTIF SÉCURITÉ : sans relation entrante, le générateur ne
            # peut déterminer AUCUN propriétaire pour la route de règlement,
            # qui accepte alors n'importe quel appelant authentifié pour
            # n'importe quel enregistrement (IDOR). Même exigence que pour
            # 'increments'/'decrements' ci-dessous -- une relation doit
            # exister pour savoir QUI possède la ligne qu'on encaisse.
            has_owner_relation = any(
                (rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity)
                or (rel["type"] == "belongsTo" and rel["source"] == entity)
                for rel in self.relations
            )
            if not has_owner_relation:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable', mais aucune relation ne désigne qui "
                    f"possède un enregistrement de '{entity}' (ex. 'Client hasMany {entity}') -- sans elle, "
                    f"la route de règlement ne pourrait vérifier qui a le droit de payer."
                )
            # LEVÉ AU POINT 87. Le point 81 refusait ici toute entité possédée
            # TRANSITIVEMENT, parce que la route de règlement comparait la clé
            # étrangère de propriété à `current_user_id` — or sous chaîne cette
            # colonne porte un id d'enregistrement intermédiaire, pas un id de
            # compte. Le refus protégeait donc d'une comparaison fausse, pas
            # d'une impossibilité : la même brique 11 fournissait déjà, dans
            # `_owner_lookup_sql`, la jointure qui rend l'id de COMPTE. La route
            # l'emploie désormais, et la comparaison redevient exacte.
            #
            # Ce qui garde la brique sûre n'a pas bougé : la chaîne doit
            # remonter à un acteur (refus du point 81, plus haut), le montant
            # doit rester incalculable par le client (refus du point 79, dans le
            # recoupement plus bas), et une relation entrante doit exister
            # (juste au-dessus). Aucun de ces trois refus n'est affaibli.
            self.payable_fields.append({"entity": entity, "field": field})

    def _valider_regle_restrictedTo(self):
        """Valide la règle 'restrictedTo' (point 112). Contrairement à
        'public'/'ownedBy'/'requiresOwn', rien ne vérifiait qu'un champ ou un
        acteur référencé par 'restrictedTo' existe réellement. Une faute de
        frappe sur le nom du champ ou de l'acteur désactivait silencieusement
        la restriction : _audit_security_rules ne trouverait jamais de
        correspondance, sans qu'aucun avertissement n'apparaisse -- exactement
        le genre de défaut que ownedBy/requiresOwn refusent déjà à la
        compilation."""
        for rule in self.rules:
            if rule["type"] != "restrictedTo":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' doit référencer "
                    f"'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' cible l'entité "
                    f"'{entity}' qui n'existe pas."
                )
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' cible le champ "
                    f"'{entity}.{field}', qui n'est pas un attribut déclaré -- "
                    f"une faute de frappe désactiverait silencieusement la "
                    f"restriction."
                )
            actor = rule["value"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure : la règle 'restrictedTo' sur "
                    f"'{entity}.{field}' restreint à l'acteur '{actor}', qui "
                    f"n'est pas un acteur déclaré."
                )

    def _valider_champs_masques(self):
        """Valide les règles ``hidden`` et prépare les champs à masquer."""
        self.masked_fields = set()
        for rule in self.rules:
            if rule["type"] != "hidden":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'hidden' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'hidden' cible l'entité '{entity}' qui n'existe pas.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : la règle 'hidden' référence le champ '{field}', qui n'est pas un attribut "
                    f"déclaré de '{entity}' (ou est 'id', qui ne peut pas être masqué)."
                )
            self.masked_fields.add((entity, field))

    def _valider_champs_categorises(self):
        """Valide les règles ``categorized`` après les champs ``hidden``."""
        self.categorized_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "categorized":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'categorized' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'categorized' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure : 'categorized' cible le champ '{entity}.{field}', qui doit être un attribut "
                    f"Integer ou Float déclaré (reçu : {field_type or 'champ inexistant'})."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'categorized' -- incompatible : "
                    f"'hidden' retire le champ, 'categorized' le remplace par une catégorie dérivée de sa valeur."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'categorized' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            seen_fields.add((entity, field))

            clauses = rule["value"]
            if len(clauses) < 2:
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' doit déclarer au moins un seuil ('below') "
                    f"et un palier de secours ('otherwise')."
                )
            for clause in clauses[:-1]:
                if "otherwise" in clause:
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' -- seul le DERNIER palier peut être "
                        f"'otherwise' (palier de secours), reçu ailleurs dans la liste."
                    )
            if "otherwise" not in clauses[-1]:
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' doit se terminer par un palier 'otherwise' "
                    f"(palier de secours qui couvre toute valeur au-delà du dernier seuil)."
                )
            thresholds = [clause["below"] for clause in clauses[:-1]]
            if thresholds != sorted(set(thresholds)) or len(thresholds) != len(set(thresholds)):
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' -- les seuils 'below' doivent être "
                    f"strictement croissants (reçu : {thresholds})."
                )
            if any(not clause["label"].strip() for clause in clauses):
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' -- chaque palier doit avoir un libellé non vide."
                )
            self.categorized_fields.append({"entity": entity, "field": field, "clauses": clauses})

    def _valider_champs_generes(self):
        """Valide les pseudonymes générés côté serveur."""
        self.generated_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "generated":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'generated' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'generated' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                raise ASTValidationError(
                    f"Structure : 'generated' cible le champ '{entity}.{field}', qui doit être un attribut "
                    f"String déclaré (reçu : {field_type or 'champ inexistant'}) -- un pseudonyme est toujours "
                    f"du texte court."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'generated' -- incompatible : "
                    f"'generated' produit déjà une valeur sûre à afficher, la masquer en plus n'a pas de sens."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'generated' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            seen_fields.add((entity, field))
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'generated', mais '{entity}.Create' est 'public' -- "
                    f"incompatible : 'generated' exige un appelant authentifié dont dériver le pseudonyme."
                )
            self.generated_fields.append({"entity": entity, "field": field})

    def _valider_champs_horodates(self):
        """Valide les instants de création attribués par le serveur."""
        self.timestamp_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "timestamp":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'timestamp' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'timestamp' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "DateTime":
                indice = (
                    " -- 'Date' tronquerait l'heure que le serveur connaît, et deux enregistrements du même jour "
                    "ne seraient plus ordonnables" if field_type == "Date" else ""
                )
                raise ASTValidationError(
                    f"Structure : 'timestamp' cible le champ '{entity}.{field}', qui doit être "
                    f"un attribut DateTime déclaré (reçu : {field_type or 'champ inexistant'}){indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'timestamp' -- "
                    f"incompatible : le client ne peut pas l'écrire et ne pourrait pas le lire, "
                    f"donc ce champ n'existerait nulle part."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'timestamp' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            if any(timestamp["entity"] == entity for timestamp in self.timestamp_fields):
                other = next(timestamp["field"] for timestamp in self.timestamp_fields if timestamp["entity"] == entity)
                raise ASTValidationError(
                    f"Structure : '{entity}' porte deux champs 'timestamp' ('{other}' et "
                    f"'{field}') -- tous deux recevraient le MÊME instant de création. "
                    f"Un horodatage de modification serait une autre brique, pas celle-ci."
                )
            seen_fields.add((entity, field))
            self.timestamp_fields.append({"entity": entity, "field": field})

    def _valider_champs_numerotes(self):
        """Valide les numéros lisibles générés côté serveur."""
        self.numbered_fields = []
        for rule in self.rules:
            if rule["type"] != "numbered":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'numbered' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'numbered' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                indice = (
                    " -- un 'UUID' vérifie sa forme depuis le point 101, et un numéro lisible n'en a pas la forme"
                    if field_type == "UUID" else ""
                )
                raise ASTValidationError(
                    f"Structure : 'numbered' cible le champ '{entity}.{field}', qui doit "
                    f"être un attribut String déclaré (reçu : {field_type or 'champ inexistant'}){indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et "
                    f"'numbered' -- incompatible : le client ne peut pas l'écrire et ne "
                    f"pourrait pas le lire, donc ce numéro n'existerait pour personne."
                )
            if any(numbered["entity"] == entity and numbered["field"] == field for numbered in self.numbered_fields):
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'numbered' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            self._valider_gabarit_de_numero(entity, field, rule["value"])
            self.numbered_fields.append({
                "entity": entity, "field": field, "format": rule["value"],
                "periode": self._periode_du_gabarit(rule["value"]),
            })

    def _valider_champs_enumeres(self):
        """Valide les champs texte limités à une liste de valeurs."""
        self.enumerated_fields = {}
        for rule in self.rules:
            if rule["type"] != "oneOf":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'oneOf' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'oneOf' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("String", "Text"):
                raise ASTValidationError(
                    f"Structure : 'oneOf' cible '{entity}.{field}', qui doit être un champ String ou Text "
                    f"(reçu : {field_type or 'champ inexistant'}) — pour un nombre, 'min'/'max' ou "
                    f"'categorized' disent déjà cela."
                )
            values = rule["value"]
            if len(values) < 2:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' n'énumère qu'une valeur — "
                    f"un champ qui n'a qu'une valeur possible n'a pas besoin d'être saisi."
                )
            empty_values = [value for value in values if not value.strip()]
            if empty_values:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' contient une valeur vide — "
                    f"elle serait indistinguable d'un champ non rempli à l'écran."
                )
            duplicates = [value for value in set(values) if values.count(value) > 1]
            if duplicates:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' répète "
                    f"{', '.join(repr(duplicate) for duplicate in sorted(duplicates))} — une liste de choix "
                    f"qui propose deux fois la même chose est une erreur de saisie."
                )
            if entity in self.enumerated_fields and field in self.enumerated_fields[entity]:
                raise ASTValidationError(
                    f"Structure : deux règles 'oneOf' sur '{entity}.{field}' — laquelle des deux listes s'appliquerait ?"
                )
            if any(generated["entity"] == entity and generated["field"] == field for generated in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'oneOf' — "
                    f"le serveur l'écrit lui-même, la liste de choix ne serait jamais lue."
                )
            self.enumerated_fields.setdefault(entity, {})[field] = list(values)

    def _valider_capacites_de_liste(self):
        """Valide les filtres et tris déclarés, sans ouvrir un langage de requête.

        BRIQUE B3. La route ne reçoit ni opérateur, ni expression, ni champ
        libre : chaque paramètre de filtre et chaque colonne de tri sont
        nommés dans la spec. Les champs retirés ou transformés en lecture sont
        refusés ici, car un filtre exact permettrait d'en déduire la valeur par
        différence de compte (oracle), même si la réponse ne contient jamais
        le champ.
        """
        self.filterable_fields = []
        self.sortable_fields = []
        seen_filters = set()
        seen_sorts = set()
        has_read = {
            action["target"].split(".", 1)[0]
            for workflow in self.workflows
            for action in workflow["actions"]
            if action["type"] == "Read"
        }

        def reference_parts(rule, kind):
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : la règle '{kind}' doit référencer "
                    f"'Entite.Read', reçu '{reference}'."
                )
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle '{kind}' cible l'entité "
                    f"'{entity}' qui n'existe pas."
                )
            if action != "Read":
                raise ASTValidationError(
                    f"Structure : '{kind}' ne vaut que sur une route Read "
                    f"(reçu '{reference}')."
                )
            if entity not in has_read:
                raise ASTValidationError(
                    f"Structure : '{reference}' n'a aucune route de lecture "
                    f"dans les workflows."
                )
            field = rule.get("field")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : '{kind}' cible le champ '{entity}.{field}', "
                    "qui n'est pas un attribut déclaré."
                )
            if field in self.LIST_QUERY_RESERVED:
                raise ASTValidationError(
                    f"Structure : le champ '{entity}.{field}' ne peut pas être "
                    f"{kind} : son nom est réservé aux paramètres de liste "
                    "(limit, offset, sort, direction)."
                )
            return entity, field

        def refuser_oracle(entity, field, kind):
            type_champ = self.entities[entity][field]
            if (entity, field) in self.masked_fields:
                raison = "hidden : le compter révélerait une valeur masquée"
            elif any(item["entity"] == entity and item["field"] == field
                     for item in self.categorized_fields):
                raison = "categorized : le compter révélerait le nombre remplacé par un libellé"
            elif type_champ == "Upload":
                raison = "Upload : le compter révélerait l'existence d'un fichier"
            else:
                compact = field.lower().replace("-", "_")
                if any(part in compact for part in self.LIST_QUERY_SECRET_PARTS):
                    raison = "nom de secret : le compter révélerait une donnée sensible"
                else:
                    return type_champ
            raise ASTValidationError(
                f"Sécurité : '{entity}.{field}' ne peut pas être {kind} : "
                f"{raison}. Un filtre ou un tri est un oracle ; déclarer un "
                "champ visible et non transformé."
            )

        for rule in self.rules:
            kind = rule["type"]
            if kind not in ("filter", "sort"):
                continue
            entity, field = reference_parts(rule, kind)
            type_champ = refuser_oracle(entity, field, kind)
            if type_champ not in self.LIST_QUERY_TYPES:
                raise ASTValidationError(
                    f"Structure : '{kind}' ne peut viser que les champs scalaires "
                    f"déclarés ({', '.join(self.LIST_QUERY_TYPES)}), reçu "
                    f"'{entity}.{field}: {type_champ}'."
                )
            cible = (entity, field)
            if kind == "filter":
                if cible in seen_filters:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'filter' sur "
                        f"'{entity}.{field}' -- une seule déclaration suffit."
                    )
                seen_filters.add(cible)
                self.filterable_fields.append({"entity": entity, "field": field})
            else:
                if cible in seen_sorts:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'sort' sur "
                        f"'{entity}.{field}' -- une seule déclaration suffit."
                    )
                seen_sorts.add(cible)
                self.sortable_fields.append({"entity": entity, "field": field})

    def _valider_champs_derives(self):
        """Valide les champs numériques calculés depuis une ligne liée."""
        self.derived_fields = []
        for rule in self.rules:
            if rule["type"] != "derivedFrom":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            factor = rule["factor"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' doit référencer 'Entite.champ derivedFrom Entite.champ by champ', "
                    f"reçu '{reference} derivedFrom {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : 'derivedFrom' cible l'entité '{entity}' qui n'existe pas.")
            if source_entity not in self.entities:
                raise ASTValidationError(f"Structure : 'derivedFrom' lit l'entité '{source_entity}' qui n'existe pas.")
            field_type = self.entities[entity].get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' calcule '{entity}.{field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {field_type or 'champ inexistant'})."
                )
            source_type = self.entities[source_entity].get(source_field)
            if source_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit '{source_entity}.{source_field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {source_type or 'champ inexistant'})."
                )
            factor_type = self.entities[entity].get(factor)
            if factor_type != "Integer":
                raise ASTValidationError(
                    f"Structure : 'derivedFrom ... by {factor}' exige que '{entity}.{factor}' soit un attribut "
                    f"Integer déclaré (reçu : {factor_type or 'champ inexistant'}) -- on multiplie par une quantité."
                )
            required_fields = {r["reference"] for r in self.rules if r.get("type") == "required"}
            if f"{entity}.{factor}" not in required_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{factor}' sert de multiplicateur à 'derivedFrom' et doit donc porter "
                    f"'rule {entity}.{factor} required' -- sinon un client qui l'omet ferait calculer sur du vide."
                )
            if factor == field:
                raise ASTValidationError(f"Structure : '{entity}.{field}' ne peut pas être son propre multiplicateur.")
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'derivedFrom' -- incompatible : "
                    f"un montant calculé qu'on ne peut pas lire ne peut pas être vérifié."
                )
            if any(g["entity"] == entity and g["field"] == field for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'derivedFrom' -- deux façons "
                    f"concurrentes de le peupler côté serveur, il faut choisir."
                )
            if any(d["entity"] == entity and d["field"] == field for d in self.derived_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte plusieurs règles 'derivedFrom' -- un seul calcul par champ."
                )
            has_source_relation = any(
                (rel["type"] in ("hasMany", "hasOne")
                 and rel["source"] == source_entity and rel["target"] == entity)
                or (rel["type"] == "belongsTo"
                    and rel["source"] == entity and rel["target"] == source_entity)
                for rel in self.relations
            )
            if not has_source_relation:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit '{source_entity}.{source_field}' depuis '{entity}', ce qui exige "
                    f"une relation entre les deux (ex. '{source_entity} hasMany {entity}'), absente ici -- sans "
                    f"elle, rien ne dit QUELLE ligne de '{source_entity}' lire."
                )
            owners = {v for (ent, _act), v in self.ownership_rules.items() if ent == entity}
            if owners and source_entity in owners:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit '{source_entity}', qui est aussi le propriétaire de "
                    f"'{entity}' (règle 'ownedBy') -- sa clé étrangère vient du jeton, pas du client, donc "
                    f"aucune ligne de '{source_entity}' ne peut être désignée à la création."
                )
            if not owners:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' sur '{entity}.{field}' exige que '{entity}' ait un propriétaire "
                    f"(une règle 'ownedBy') -- c'est lui qui distingue la clé étrangère peuplée par le serveur "
                    f"de celle que le client fournit pour désigner la ligne à lire."
                )
            self.derived_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
                "factor": factor,
            })

    def _valider_champs_agreges(self):
        """Valide les champs calculés par somme des lignes enfants."""
        self.aggregated_fields = []
        for rule in self.rules:
            if rule["type"] != "sumOf":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure : 'sumOf' doit référencer 'Entite.champ sumOf Entite.champ', "
                    f"reçu '{reference} sumOf {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : 'sumOf' cible l'entité '{entity}' qui n'existe pas.")
            if source_entity not in self.entities:
                raise ASTValidationError(f"Structure : 'sumOf' additionne l'entité '{source_entity}' qui n'existe pas.")
            field_type = self.entities[entity].get(field)
            if field_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'sumOf' calcule '{entity}.{field}', qui doit être un attribut "
                    f"Money, Float ou Integer déclaré (reçu : {field_type or 'champ inexistant'})."
                )
            source_type = self.entities[source_entity].get(source_field)
            if source_type not in ("Money", "Float", "Integer"):
                raise ASTValidationError(
                    f"Structure : 'sumOf' additionne '{source_entity}.{source_field}', qui doit être un "
                    f"attribut Money, Float ou Integer déclaré (reçu : {source_type or 'champ inexistant'})."
                )
            if source_entity == entity:
                raise ASTValidationError(
                    f"Structure : 'sumOf' fait de '{entity}.{field}' la somme d'un champ de '{entity}' lui-même "
                    f"-- une entité ne peut pas s'additionner. La somme porte sur une entité ENFANT "
                    f"(ex. 'Commande hasMany Ligne')."
                )
            child_relation = any(
                (rel["type"] in ("hasMany", "hasOne")
                 and rel["source"] == entity and rel["target"] == source_entity)
                or (rel["type"] == "belongsTo"
                    and rel["source"] == source_entity and rel["target"] == entity)
                for rel in self.relations
            )
            if not child_relation:
                raise ASTValidationError(
                    f"Structure : 'sumOf' additionne '{source_entity}' depuis '{entity}', ce qui exige "
                    f"une relation parent-enfant (ex. '{entity} hasMany {source_entity}'), absente ici -- "
                    f"sans elle, rien ne dit QUELLES lignes de '{source_entity}' additionner, et la somme "
                    f"porterait sur la table entière."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'sumOf' -- incompatible : "
                    f"un total calculé qu'on ne peut pas lire ne peut pas être vérifié."
                )
            if any(g["entity"] == entity and g["field"] == field for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'sumOf' -- deux façons "
                    f"concurrentes de le peupler côté serveur, il faut choisir."
                )
            if any(d["entity"] == entity and d["field"] == field for d in self.derived_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte à la fois 'derivedFrom' et 'sumOf' -- deux "
                    f"calculs concurrents pour un seul champ. 'derivedFrom' lit UNE ligne liée, 'sumOf' "
                    f"additionne des enfants : choisir lequel."
                )
            if any(a["entity"] == entity and a["field"] == field for a in self.aggregated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte plusieurs règles 'sumOf' -- une seule somme par champ."
                )
            source_owners = {v for (ent, _act), v in self.ownership_rules.items() if ent == source_entity}
            if not source_owners:
                raise ASTValidationError(
                    f"Structure : 'sumOf' additionne '{source_entity}', qui n'a pas de propriétaire "
                    f"(une règle 'ownedBy') -- c'est lui qui distingue la clé étrangère peuplée par le "
                    f"serveur de celle que le client fournit pour désigner le parent. Sans elle, "
                    f"n'importe quel compte pourrait ajouter une ligne au total d'un tiers."
                )
            self.aggregated_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
            })

    def _valider_securite_calculs_paiement(self):
        """Recoupe champs serveur, bornes et montants encaissables."""
        derived = {(item["entity"], item["field"]) for item in self.derived_fields}
        sums = {(item["entity"], item["field"]): item for item in self.aggregated_fields}
        server_fields = (
            derived
            | set(sums)
            | {(item["entity"], item["field"]) for item in self.generated_fields}
            | {(item["entity"], item["field"]) for item in self.timestamp_fields}
            | {(item["entity"], item["field"]) for item in self.numbered_fields}
        )
        for (entity, field), constraints in sorted(self.field_constraints.items()):
            if (entity, field) not in server_fields:
                continue
            bounds = [name for name in ("min", "max") if name in constraints]
            if bounds:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte "
                    f"'{ '/'.join(bounds) }' alors que le SERVEUR calcule ce champ : il "
                    f"est absent du corps de requête, donc la borne ne s'appliquerait "
                    f"à rien. La retirer, ou borner le champ d'où la valeur vient."
                )
            if "required" in constraints:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'required' alors que le SERVEUR "
                    f"le calcule : le client ne peut pas le fournir, et le contrat "
                    f"dirait à la fois « à remplir » et « à ne pas envoyer »."
                )

        for payable in self.payable_fields:
            entity, field = payable["entity"], payable["field"]
            if (entity, field) not in derived and (entity, field) not in sums:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable' mais le client peut l'écrire -- "
                    f"le créateur d'un '{entity}' en devient le propriétaire, donc le payeur : il "
                    f"fixerait lui-même ce qu'il règle. Ajouter une règle qui fait calculer le "
                    f"montant par le serveur, par exemple "
                    f"'rule {entity}.{field} derivedFrom Article.prix by quantite', ou "
                    f"'rule {entity}.{field} sumOf Ligne.sousTotal' pour un panier."
                )
            total = sums.get((entity, field))
            if total is not None:
                source = (total["source_entity"], total["source_field"])
                if source not in derived and source not in sums:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est 'payable' et somme "
                        f"'{total['source_entity']}.{total['source_field']}', que le client peut "
                        f"écrire -- additionner un montant fourni par le payeur donne un total que le "
                        f"payeur fixe encore, en une addition de plus. Faire calculer la ligne par le "
                        f"serveur, par exemple 'rule {total['source_entity']}."
                        f"{total['source_field']} derivedFrom Article.prix by quantite'."
                    )

    def _valider_effets_compteurs(self):
        """Valide les effets de compteur déclenchés à la création."""
        self.reputation_rules = []
        for rule in self.rules:
            if rule["type"] not in ("decrements", "increments"):
                continue
            direction = rule["type"]
            trigger_ref, target_ref = rule["reference"], rule["value"]
            if "." not in trigger_ref or "." not in target_ref:
                raise ASTValidationError(
                    f"Structure : la règle '{direction}' doit référencer 'Entite.Create {direction} Entite.champ', "
                    f"reçu '{trigger_ref} {direction} {target_ref}'."
                )
            trigger_entity, trigger_action = trigger_ref.split(".", 1)
            target_entity, target_field = target_ref.split(".", 1)
            if trigger_entity not in self.entities:
                raise ASTValidationError(f"Structure : '{direction}' référence l'entité '{trigger_entity}' qui n'existe pas.")
            if trigger_action != "Create":
                raise ASTValidationError(
                    f"Structure : '{direction}' n'est pris en charge que sur 'Create' pour l'instant "
                    f"(reçu '{trigger_entity}.{trigger_action}')."
                )
            if target_entity not in self.entities:
                raise ASTValidationError(f"Structure : '{direction}' référence l'entité '{target_entity}' qui n'existe pas.")
            target_type = self.entities[target_entity].get(target_field)
            if target_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure : '{direction}' cible le champ '{target_entity}.{target_field}', qui doit être "
                    f"un attribut Integer ou Float déclaré (reçu : {target_type or 'champ inexistant'})."
                )
            matching_relation = any(
                (rel["type"] in ("hasMany", "hasOne")
                 and rel["source"] == target_entity and rel["target"] == trigger_entity)
                or (rel["type"] == "belongsTo"
                    and rel["target"] == target_entity and rel["source"] == trigger_entity)
                for rel in self.relations
            )
            if not matching_relation:
                raise ASTValidationError(
                    f"Structure : '{direction}' sur '{trigger_entity}.Create' vers '{target_entity}.{target_field}' "
                    f"exige une relation entre les deux (ex. '{target_entity} hasMany {trigger_entity}'), absente ici."
                )
            amount_field = rule.get("amount_field")
            if amount_field:
                amount_type = self.entities[trigger_entity].get(amount_field)
                if amount_type != "Integer":
                    raise ASTValidationError(
                        f"Structure : '{direction} ... by {amount_field}' désigne un champ de "
                        f"'{trigger_entity}' qui doit être un Integer déclaré "
                        f"(reçu : {amount_type or 'champ inexistant'})."
                    )
                required = {r["reference"] for r in self.rules if r.get("type") == "required"}
                if f"{trigger_entity}.{amount_field}" not in required:
                    raise ASTValidationError(
                        f"Structure : '{trigger_entity}.{amount_field}' sert de quantité à "
                        f"'{direction}' : il lui faut 'rule {trigger_entity}.{amount_field} "
                        f"required', sinon un client qui l'omet ferait décompter sur du vide."
                    )
            self.reputation_rules.append({
                "trigger_entity": trigger_entity, "target_entity": target_entity,
                "target_field": target_field, "amount": rule.get("amount"),
                "amount_field": amount_field, "direction": direction,
            })

    def _valider_proprietaire_paiement(self):
        """Vérifie qu'un montant payable remonte réellement jusqu'à un compte."""
        for payable in self.payable_fields:
            entity = payable["entity"]
            if entity in self.transitive_ownership:
                continue
            targets = {
                rule["target_entity"] for rule in self.reputation_rules
                if rule["trigger_entity"] == entity
            }
            actor_parents = {
                (rel["source"] if rel["type"] in ("hasMany", "hasOne") else rel["target"])
                for rel in self.relations
                if (rel["type"] in ("hasMany", "hasOne") and rel["target"] == entity)
                or (rel["type"] == "belongsTo" and rel["source"] == entity)
            } & set(self.actors) - targets
            if not actor_parents:
                raise ASTValidationError(
                    f"Structure : '{entity}.{payable['field']}' est 'payable', mais aucun "
                    f"ACTEUR ne possède un enregistrement de '{entity}'. Une relation vers "
                    f"une table métier ne suffit pas : la colonne qu'elle produit porte "
                    f"l'id de cette ligne, pas celui d'un compte, et la route de règlement "
                    f"la compare à l'appelant. Déclarer 'un_acteur hasMany {entity}', ou "
                    f"rattacher '{entity}' à un acteur à travers son parent "
                    f"('rule {entity}.Read ownedBy <Parent>')."
                )

    def _valider_regles_liberation(self):
        """Valide les transitions qui rendent un compteur décrémenté."""
        self.release_rules = []
        for rule in self.rules:
            if rule["type"] != "releases":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'releases' doit référencer 'Entite.champ', "
                    f"reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'releases' cible l'entité '{entity}' qui n'existe pas."
                )
            choices = self.enumerated_fields.get(entity, {}).get(field)
            if not choices:
                raise ASTValidationError(
                    f"Structure : 'releases' exige que '{entity}.{field}' porte un 'oneOf' — "
                    f"sans liste de valeurs, une faute de frappe donnerait une règle qui ne se déclenche jamais."
                )
            if rule["value"] not in choices:
                raise ASTValidationError(
                    f"Structure : 'releases' se déclenche sur la valeur {rule['value']!r}, "
                    f"absente du 'oneOf' de '{entity}.{field}' "
                    f"({', '.join(repr(choice) for choice in choices)}) — elle ne surviendrait jamais."
                )
            released_entity = rule["entity"]
            if released_entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'releases' nomme l'entité '{released_entity}', qui n'existe pas."
                )
            decrements = [
                item for item in self.reputation_rules
                if item["trigger_entity"] == released_entity and item["direction"] == "decrements"
            ]
            if not decrements:
                raise ASTValidationError(
                    f"Structure : 'releases {released_entity}' ne libérerait rien — cette entité ne porte "
                    f"aucune règle 'decrements'. C'est ce qu'un décompte a consommé que l'on rend."
                )
            if not any(rel["source"] == entity and rel["target"] == released_entity for rel in self.relations):
                raise ASTValidationError(
                    f"Structure : 'releases' exige une relation '{entity} hasMany {released_entity}' — "
                    f"sans elle, rien ne dit quelles lignes de {released_entity} dépendent de ce {entity}."
                )
            if any(item["entity"] == entity and item["field"] == field for item in self.release_rules):
                raise ASTValidationError(
                    f"Structure : deux règles 'releases' sur '{entity}.{field}' — la première libération "
                    f"rendrait déjà le décompte, la seconde le rendrait une deuxième fois."
                )
            self.release_rules.append({
                "entity": entity, "field": field, "value": rule["value"], "releases": released_entity,
            })

    def _valider_ui_overrides(self):
        """Valide les entités et champs référencés par le bloc ``ui``."""
        self.ui_overrides = {}
        for override in self.ui_overrides_raw:
            entity = override["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : le bloc 'ui {entity}' cible une entité qui n'existe pas.")
            primary = override.get("primary")
            if primary and primary not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : 'ui {entity}' référence 'primary: {primary}', qui n'est pas un attribut de '{entity}'."
                )
            order = override.get("order")
            if order:
                unknown = [field for field in order if field not in self.entities[entity]]
                if unknown:
                    raise ASTValidationError(
                        f"Structure : 'ui {entity}' référence des champs inconnus dans 'order' : {unknown}."
                    )
            self.ui_overrides[entity] = {
                "theme": override.get("theme"), "primary": primary, "order": order,
            }

    def _valider_landing(self):
        """Normalise le contenu éditorial conservé pour le contrat frontend."""
        self.landing = None
        if self.landing_raw is None:
            return
        for obsolete in ("mode", "template"):
            if self.landing_raw.get(obsolete):
                print(f"⚠️  'landing / {obsolete}' est obsolète depuis le pivot "
                      f"(point 41 de docs/design_decisions.md) : monl ne génère "
                      f"plus de page d'accueil — seul 'brief' est transmis à l'IA frontend.")
        sections = []
        for section in self.landing_raw.get("sections") or []:
            title = (section.get("title") or "").strip()
            body = (section.get("body") or "").strip()
            if not title or not body:
                raise ValueError(
                    "SEMANTIC_ERROR: une 'section' de 'landing' exige un titre ET un texte non vides "
                    f"(trouvé : titre={title!r}, texte={body!r})."
                )
            sections.append({"title": title, "body": body})
        faq = []
        for entry in self.landing_raw.get("faq") or []:
            question = (entry.get("question") or "").strip()
            answer = (entry.get("answer") or "").strip()
            if not question or not answer:
                raise ValueError(
                    "SEMANTIC_ERROR: une 'question' de 'landing' exige une question ET une réponse non vides "
                    f"(trouvé : question={question!r}, réponse={answer!r})."
                )
            faq.append({"question": question, "answer": answer})
        self.landing = {"brief": self.landing_raw.get("brief"), "sections": sections,
                        "faq": faq, "links": self._valider_liens_sortants()}

    #: Ce qu'un navigateur sait ouvrir depuis un pied de page. `tel:` et
    #: `mailto:` en font partie : sur un site de commerce, ce sont souvent les
    #: DEUX liens qui comptent le plus.
    SCHEMES_DE_LIEN = ("https://", "http://", "mailto:", "tel:")

    def _valider_liens_sortants(self):
        """Normalise les liens du pied de page — ou refuse en l'expliquant.

        monl ne VÉRIFIE pas qu'une adresse répond : il ne fait aucun appel
        réseau, et le prétendre serait mentir (même frontière qu'au point 83
        pour les images distantes). Ce qu'il vérifie, c'est qu'un navigateur
        saura l'ouvrir — un « instagram.com/atelier » sans schéma est lu comme
        un chemin RELATIF et mène à une page inexistante du site lui-même.
        Un lien qui ne marche pas est pire qu'un lien absent : il se voit.
        """
        liens, libelles, adresses = [], set(), set()
        for entree in self.landing_raw.get("links") or []:
            label = (entree.get("label") or "").strip()
            url = (entree.get("url") or "").strip()
            if not label or not url:
                raise ValueError(
                    "SEMANTIC_ERROR: un 'link' de 'landing' exige un libellé ET une "
                    f"adresse non vides (trouvé : libellé={label!r}, adresse={url!r})."
                )
            if not url.lower().startswith(self.SCHEMES_DE_LIEN):
                raise ValueError(
                    f"SEMANTIC_ERROR: le lien « {label} » porte l'adresse {url!r}, "
                    "que le navigateur lira comme un chemin du site lui-même. "
                    "Écrire l'adresse complète : "
                    + ", ".join(f"'{s}…'" for s in self.SCHEMES_DE_LIEN) + "."
                )
            repere = label.casefold()
            if repere in libelles:
                raise ValueError(
                    f"SEMANTIC_ERROR: deux liens de 'landing' portent le libellé "
                    f"« {label} ». Un pied de page qui répète un libellé fait "
                    "hésiter sur lequel suivre."
                )
            if url in adresses:
                raise ValueError(
                    f"SEMANTIC_ERROR: l'adresse {url!r} est déclarée deux fois "
                    "dans 'landing'."
                )
            libelles.add(repere)
            adresses.add(url)
            liens.append({"label": label, "url": url})
        return liens

    def _valider_prestataire(self, nom):
        """Résout le prestataire d'encaissement — ou refuse en l'expliquant."""
        nom = str(nom).lower()
        if nom in PRESTATAIRES:
            return nom
        if nom in PRESTATAIRES_ECARTES:
            raise ASTValidationError(
                f"Structure : le prestataire '{nom}' n'est pas implémenté par "
                f"monl, et ce n'est pas un oubli : {PRESTATAIRES_ECARTES[nom]}. "
                f"Prestataires disponibles : {', '.join(sorted(PRESTATAIRES))}.")
        raise ASTValidationError(
            f"Structure : prestataire de paiement inconnu : '{nom}'. "
            f"Disponibles : {', '.join(sorted(PRESTATAIRES))}.")

    def _valider_devise(self, code):
        """Résout un code ISO en {code, exponent} — ou refuse en l'expliquant.

        L'exposant est calculé ICI et une seule fois : le générateur le LIT, il
        ne le redérive pas. Deux tables finiraient par diverger, et une
        divergence d'unité se paie sur le relevé bancaire (voir DEVISES).
        """
        code = str(code).upper()
        if code in DEVISES:
            return {"code": code, "exponent": DEVISES[code]}
        # Trois décimales : refusées NOMMÉMENT, pour que le message n'envoie
        # pas chercher une faute de frappe dans un code parfaitement valide.
        if code in {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}:
            raise ASTValidationError(
                f"Structure : la devise '{code}' a trois décimales, et les "
                f"prestataires de paiement y imposent un arrondi particulier "
                f"que monl ne sait pas encore appliquer. Elle est refusée "
                f"plutôt qu'encaissée à peu près.")
        raise ASTValidationError(
            f"Structure : devise '{code}' inconnue de monl. Elle n'est pas "
            f"devinée à deux décimales : une devise sans sous-unité facturée "
            f"comme l'euro multiplierait chaque montant par cent. Devises "
            f"reconnues : {', '.join(sorted(DEVISES))}.")

    def _valider_capacites(self):
        """Valide les capacités déclarées et prépare l'authentification B4."""
        known_capabilities = {"auth", "payment"}
        names = [capability["name"] for capability in self.capabilities_raw]
        unknown = [name for name in names if name not in known_capabilities]
        if unknown:
            raise ASTValidationError(
                f"Structure : capacité(s) inconnue(s) déclarée(s) avec 'capability' : {', '.join(unknown)}. "
                f"Capacités reconnues : {', '.join(sorted(known_capabilities))}."
            )
        self.capabilities = list(dict.fromkeys(names))
        self.auth_identifier = self._valider_identifiant_de_compte(self.capabilities_raw)

        allowed_auth_options = {
            "name", "identifier", "phone_prefix", "lockout", "password_reset",
            "refresh_tokens", "totp",
        }
        # BRIQUE 2a : 'currency' est la première option qui n'appartient PAS à
        # 'capability auth'. La grammaire partage un seul jeu de propriétés
        # entre toutes les capacités — c'est donc ici, et nulle part ailleurs,
        # que chaque option est rattachée à sa capacité.
        allowed_payment_options = {"currency", "provider"}
        options_par_capacite = {
            "auth": allowed_auth_options - {"name"},
            "payment": allowed_payment_options,
        }
        features = {}
        self.payment_currency = None
        self.payment_provider = None
        for capability in self.capabilities_raw:
            nom = capability["name"]
            options = set(capability) - {"name"}
            permises = options_par_capacite.get(nom, set())
            hors_sujet = options - permises
            if hors_sujet:
                # Nommer la capacité qui ACCEPTE l'option, quand elle existe :
                # « currency n'a pas de sens ici » enverrait chercher une faute
                # de frappe alors que la ligne est simplement au mauvais
                # endroit.
                accueil = {opt: cap
                           for cap, opts in options_par_capacite.items()
                           for opt in opts}
                remedes = sorted(
                    f"'{opt}' appartient à 'capability {accueil[opt]}'"
                    for opt in hors_sujet if opt in accueil)
                inconnues = sorted(opt for opt in hors_sujet if opt not in accueil)
                detail = " ; ".join(remedes + [f"'{o}' est inconnue" for o in inconnues])
                raise ASTValidationError(
                    f"Structure : option(s) déplacée(s) ou inconnue(s) sur "
                    f"'capability {nom}' — {detail}.")
            if nom == "payment" and "provider" in capability:
                if self.payment_provider is not None:
                    raise ASTValidationError(
                        "Structure : le prestataire de paiement est déclaré "
                        "deux fois — une application encaisse par UNE seule "
                        "voie, sinon le webhook ne sait plus quelle signature "
                        "vérifier.")
                self.payment_provider = self._valider_prestataire(
                    capability["provider"])
            if nom == "payment" and "currency" in capability:
                if self.payment_currency is not None:
                    raise ASTValidationError(
                        "Structure : la devise est déclarée deux fois — une "
                        "application encaisse dans UNE seule devise, sinon "
                        "'montant' ne veut plus rien dire d'une commande à "
                        "l'autre.")
                self.payment_currency = self._valider_devise(capability["currency"])
            if nom != "auth":
                continue
            for option in ("lockout", "password_reset", "refresh_tokens", "totp"):
                if option not in capability:
                    continue
                if option in features:
                    raise ASTValidationError(
                        f"Structure : l'option '{option}' est déclarée deux fois "
                        "sur 'capability auth'.")
                features[option] = capability[option]

        lockout = features.get("lockout")
        if lockout:
            if lockout["max_attempts"] < 1:
                raise ASTValidationError(
                    "Structure : 'lockout' exige au moins 1 échec avant verrouillage.")
            if lockout["window_seconds"] < 1:
                raise ASTValidationError(
                    "Structure : la fenêtre de 'lockout' doit être exprimée en secondes positives.")
        for option, libelle in (("password_reset", "password_reset"),
                                ("refresh_tokens", "refresh_tokens")):
            if option in features and features[option] < 1:
                raise ASTValidationError(
                    f"Structure : '{libelle}' doit être une durée positive en secondes.")
        if "password_reset" in features and (
                not self.auth_identifier or "email" not in self.auth_identifier):
            raise ASTValidationError(
                "Structure : 'password_reset' exige 'capability auth' avec "
                "'identifier: email' : le message de récupération doit avoir "
                "une adresse de compte, sans deviner un champ métier.")
        self.auth_features = features

        # BRIQUE 2a : une devise déclarée sans rien à encaisser ne produit
        # RIEN. C'est le point 85 mot pour mot — refuser une règle sans effet
        # plutôt que l'ignorer en silence, sinon l'auteur croit avoir configuré
        # son application.
        #
        # LE RECOUPEMENT VIT ICI, ET C'EST UNE QUESTION D'ORDRE, PAS DE GOÛT.
        # Écrit d'abord dans `_valider_securite_calculs_paiement` — l'endroit
        # « logique », auprès des autres refus de paiement — il ne se
        # déclenchait JAMAIS : le pipeline y passe à l'étape 261, et
        # `_valider_capacites` ne pose `payment_currency` qu'à l'étape 344. La
        # garde lisait donc toujours `None`. Elle est ici parce que c'est le
        # premier moment où les DEUX informations existent : `payable_fields`
        # est posé dès l'étape 228. Même famille que le point 92 — une garde
        # qui lit une variable pas encore assignée est une garde qui ment, et
        # seul un test qui EXIGE le refus le révèle.
        if not self.payable_fields:
            declare = []
            if self.payment_currency:
                declare.append(f"la devise '{self.payment_currency['code']}'")
            if self.payment_provider:
                declare.append(f"le prestataire '{self.payment_provider}'")
            if declare:
                raise ASTValidationError(
                    f"Structure : 'capability payment' déclare "
                    f"{' et '.join(declare)}, mais aucune règle 'payable' ne "
                    f"dit quoi encaisser — cette configuration ne "
                    f"s'appliquerait à rien. Ajouter "
                    f"'rule Entite.champ payable', ou retirer ces lignes.")

        # BRIQUE 2b, SUITE : le prestataire et la devise sont déclarés
        # séparément, donc rien n'empêchait de les déclarer INCOMPATIBLES.
        # La devise EFFECTIVE est comparée, pas seulement la déclarée : sans
        # ligne `currency`, le défaut est l'euro (DEVISE_PAR_DEFAUT), et
        # `provider: fedapay` tout seul partait donc encaisser en euros chez
        # un prestataire qui n'en accepte pas. Le refus NOMME la devise
        # attendue — un message qui dirait seulement « incompatible »
        # laisserait chercher.
        prestataire = self.payment_provider or PRESTATAIRE_PAR_DEFAUT
        acceptees = DEVISES_PAR_PRESTATAIRE.get(prestataire)
        effective = (self.payment_currency or {}).get("code") or DEVISE_PAR_DEFAUT
        if acceptees is not None and effective not in acceptees:
            attendue = ", ".join(sorted(acceptees))
            constat = (f"la devise déclarée est '{effective}'"
                       if self.payment_currency else
                       f"aucune ligne 'currency' n'est déclarée, donc le "
                       f"défaut s'applique : '{effective}'")
            raise ASTValidationError(
                f"Structure : le prestataire '{prestataire}' n'encaisse qu'en "
                f"{attendue}, or {constat}. Cette "
                f"configuration compilerait sans jamais pouvoir encaisser : "
                f"le refus arrive maintenant plutôt qu'au premier vrai "
                f"paiement. Ajouter 'currency: {attendue.split(', ')[0]}' au "
                f"bloc 'capability payment'.")

    def _valider_regles_message(self):
        """Valide les notifications e-mail déclenchées par une création.

        B2 choisit délibérément une seule transition : Create. La cible
        est le compte authentifié qui vient de créer la ligne, donc son
        identifiant canonique en base. Aucun champ métier libre nommé
        email ne participe à cette décision.
        """
        self.message_rules = []
        references = set()
        for rule in self.rules:
            if rule["type"] != "sends":
                continue
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : la règle 'sends' doit référencer "
                    f"'Entite.Create', reçu '{reference}'.")
            entity, action = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'sends' cible l'entité '{entity}' qui n'existe pas.")
            if action != "Create":
                raise ASTValidationError(
                    f"Structure : 'sends' ne vaut que sur 'Entite.Create' "
                    f"(reçu '{reference}'). La transition oneOf est volontairement "
                    "hors de cette brique.")
            if reference in references:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'sends' sur '{reference}' -- "
                    "une création ne doit déclencher qu'un seul message.")
            references.add(reference)
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{reference}' est public, mais 'sends' doit "
                    "connaître le compte destinataire. Une création publique "
                    "n'offre aucune identité à laquelle écrire.")
            if not any(
                    action_["type"] == "Create" and action_["target"] == entity
                    for workflow in self.workflows
                    for action_ in workflow["actions"]):
                raise ASTValidationError(
                    f"Structure : '{reference}' porte 'sends', mais aucune route "
                    f"Create {entity} n'est déclarée -- l'envoi ne se déclencherait jamais.")
            if not self.auth_identifier or "email" not in self.auth_identifier:
                raise ASTValidationError(
                    f"Structure : '{reference}' veut envoyer un courriel, mais la spec "
                    "ne déclare pas 'capability auth' avec 'identifier: email'. "
                    "Sans cette identité de compte, monl n'a aucune adresse où écrire ; "
                    "un champ texte libre nommé 'email' ne vaut pas une adresse de compte.")

            subject = rule.get("subject", "")
            body = rule.get("body", "")
            if not subject.strip():
                raise ASTValidationError(
                    f"Structure : le sujet du message '{reference}' ne peut pas être vide.")
            if not body.strip():
                raise ASTValidationError(
                    f"Structure : le corps du message '{reference}' ne peut pas être vide.")
            if "\r" in subject or "\n" in subject:
                raise ASTValidationError(
                    f"Structure : le sujet de '{reference}' contient un saut de ligne. "
                    "Refusé pour empêcher une injection d'en-têtes SMTP (Bcc, Cc, etc.).")
            if "\r" in body or "\n" in body:
                raise ASTValidationError(
                    f"Structure : le corps de '{reference}' contient un saut de ligne brut. "
                    "Utiliser le séparateur '¶' entre les paragraphes.")
            self.message_rules.append({
                "trigger_entity": entity,
                "trigger_action": action,
                "subject": subject,
                "body": body,
            })

    def _valider_assets_et_seeds(self):
        """Valide les assets locaux et les données de démonstration."""
        self.assets = dict(self.assets_raw)
        assets_dir = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        self._verifier_forme_chemin_asset(assets_dir, "assets.dir")
        self.assets["dir"] = assets_dir
        for key in ("logo", "favicon"):
            if key not in self.assets_raw:
                continue
            value = self.assets_raw[key]
            self._verifier_forme_chemin_asset(value, f"assets.{key}")
            self._verifier_asset_present(value, f"assets.{key}")

        numeric_types = {"Integer", "Float", "Money"}
        self.seeds = []
        for seed in self.seeds_raw:
            entity = seed["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : le bloc 'seed' cible l'entité '{entity}' qui n'existe pas.")
            entity_fields = self.entities[entity]
            if seed.get("parent"):
                self._valider_parent_de_seed(entity, seed["parent"])
            for index, row in enumerate(seed["rows"], start=1):
                for field, value in row.items():
                    if field not in entity_fields:
                        raise ASTValidationError(
                            f"Structure : le bloc 'seed {entity}' (ligne {index}) référence le champ "
                            f"'{field}', qui n'est pas déclaré sur '{entity}'."
                        )
                    declared_type = entity_fields[field]
                    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
                    if declared_type in numeric_types and not is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {index}), champ '{field}' de type "
                            f"{declared_type} attend un nombre, reçu une chaîne."
                        )
                    if declared_type not in numeric_types and is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {index}), champ '{field}' de type "
                            f"{declared_type} attend une chaîne entre guillemets, reçu un nombre."
                        )
                    if declared_type == "Upload":
                        raise ASTValidationError(
                            f"Structure : un seed ne peut pas fournir '{entity}.{field}' "
                            "de type Upload. Les octets arrivent uniquement à "
                            "l'exécution par la route multipart, jamais dans la spec "
                            "ou les artefacts scellés.")
                    if declared_type == "Image":
                        location = f"seed {entity} (ligne {index}), champ '{field}'"
                        self._verifier_forme_chemin_asset(value, location, image=True)
                        self._verifier_asset_present(value, location)
            self.seeds.append(seed)

    def _valider_migrations(self):
        """Valide les opérations de schéma qui ne sont pas additives.

        Une migration décrit l'état cible de la spec, donc son ancienne
        colonne peut légitimement ne plus figurer dans ``self.entities``.
        L'ancienne forme est néanmoins conservée dans l'opération afin que le
        runtime puisse vérifier la précondition au moment où l'opérateur la
        lance, plutôt que de deviner un renommage depuis deux noms proches.
        """
        self.migrations = []
        names = set()
        seen_operations = set()
        known_types = {
            "String", "Text", "Integer", "Float", "Boolean", "Date",
            "DateTime", "Email", "UUID", "Money", "Image", "Upload",
        }
        for migration in self.migrations_raw:
            name = migration["name"]
            if name in names:
                raise ASTValidationError(
                    f"Structure : la migration '{name}' est déclarée plusieurs fois.")
            names.add(name)
            operations = []
            if not migration.get("operations"):
                raise ASTValidationError(
                    f"Structure : la migration '{name}' ne contient aucune opération.")
            for index, operation in enumerate(migration["operations"], start=1):
                reference = operation["reference"]
                if "." not in reference:
                    raise ASTValidationError(
                        f"Structure : l'opération {index} de la migration '{name}' doit "
                        f"référencer 'Entite.champ', reçu '{reference}'.")
                entity, field = reference.split(".", 1)
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure : la migration '{name}' cible l'entité '{entity}', "
                        "qui n'existe pas dans la spec courante.")
                kind = operation["kind"]
                key = (kind, entity, field, operation.get("new_name"),
                       operation.get("from_type"), operation.get("to_type"))
                if key in seen_operations:
                    raise ASTValidationError(
                        f"Structure : l'opération {index} de la migration '{name}' "
                        "est déclarée en double.")
                seen_operations.add(key)
                if kind == "rename":
                    new_field = operation["new_name"]
                    if field == new_field:
                        raise ASTValidationError(
                            f"Structure : la migration '{name}' renomme "
                            f"'{reference}' vers lui-même.")
                    if field in self.entities[entity]:
                        raise ASTValidationError(
                            f"Structure : la colonne source '{reference}' existe encore "
                            "dans la spec cible ; retirez-la avant de la renommer.")
                    if new_field not in self.entities[entity]:
                        raise ASTValidationError(
                            f"Structure : le renommage '{reference}' vers "
                            f"'{entity}.{new_field}' ne trouve pas la colonne cible "
                            "dans la spec courante.")
                    operations.append({
                        "kind": kind, "entity": entity, "table": entity.lower(),
                        "old": field, "new": new_field, "reversible": True,
                    })
                elif kind == "alter":
                    old_type = operation["from_type"]
                    new_type = operation["to_type"]
                    if old_type not in known_types or new_type not in known_types:
                        raise ASTValidationError(
                            f"Structure : la migration '{name}' porte des types "
                            f"inconnus ({old_type} -> {new_type}).")
                    if old_type == new_type:
                        raise ASTValidationError(
                            f"Structure : la migration '{name}' ne change pas le type "
                            f"de '{reference}'.")
                    actual_type = self.entities[entity].get(field)
                    if actual_type != new_type:
                        raise ASTValidationError(
                            f"Structure : la cible de '{name}' déclare '{reference}' "
                            f"en {actual_type}, mais l'opération annonce {new_type}.")
                    operations.append({
                        "kind": kind, "entity": entity, "table": entity.lower(),
                        "field": field, "from_type": old_type, "to_type": new_type,
                        "reversible": True,
                    })
                else:
                    if field in self.entities[entity]:
                        raise ASTValidationError(
                            f"Structure : la colonne retirée '{reference}' existe encore "
                            "dans la spec cible ; retirez-la avant le DROP explicite.")
                    operations.append({
                        "kind": kind, "entity": entity, "table": entity.lower(),
                        "old": field, "reversible": False,
                    })
            self.migrations.append({"name": name, "operations": operations})

    def _valider_workflows_et_collisions(self):
        """Valide les workflows et détecte les collisions d'autorité."""
        access_matrix = {}
        shared_permissions = {
            rule["reference"]: set(rule["value"])
            for rule in self.rules if rule["type"] == "sharedBy"
        }
        for workflow in self.workflows:
            actor = workflow["actor"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure : L'acteur '{actor}' dans le workflow '{workflow['name']}' n'est pas déclaré."
                )
            for action in workflow["actions"]:
                target = action["target"]
                action_type = action["type"]
                if action_type == "Execute":
                    if target not in self.custom_logic:
                        raise ASTValidationError(
                            f"Architecture : L'action Execute appelle '{target}', mais ce bloc custom n'est pas défini."
                        )
                    continue
                entity = target.split(".")[0] if "." in target else target
                if entity not in self.entities:
                    raise ASTValidationError(
                        f"Structure : L'action cible l'entité '{entity}' qui n'existe pas."
                    )
                if (entity, action_type) in self.public_actions:
                    continue
                access_matrix.setdefault(entity, {}).setdefault(action_type, set()).add(actor)

        for entity, actions in access_matrix.items():
            for action_type, authorized_actors in actions.items():
                if len(authorized_actors) <= 1 or action_type not in ("Create", "Update", "Delete"):
                    continue
                key = f"{entity}.{action_type}"
                allowed_shared = shared_permissions.get(key)
                if allowed_shared and authorized_actors.issubset(allowed_shared):
                    print(f"🤝 [SHARED_PRIVILEGE] L'action '{action_type}' sur '{entity}' est explicitement "
                          f"partagée entre [{', '.join(sorted(authorized_actors))}] via une règle 'sharedBy'.")
                    continue
                if (entity, action_type) in self.ownership_rules:
                    print(f"🔐 [SHARED_PRIVILEGE_VIA_OWNERSHIP] L'action '{action_type}' sur '{entity}' est partagée "
                          f"entre [{', '.join(sorted(authorized_actors))}], mais protégée au niveau de chaque "
                          f"enregistrement par la règle 'ownedBy' (propriétaire : "
                          f"{self.ownership_rules[(entity, action_type)]}).")
                    continue
                if (entity, action_type) in self.access_party_rules:
                    print(f"🔐 [SHARED_PRIVILEGE_VIA_ACCESS] L'action '{action_type}' sur '{entity}' est partagée "
                          f"entre [{', '.join(sorted(authorized_actors))}], mais protégée au niveau de chaque "
                          f"enregistrement par la règle 'accessibleBy' "
                          f"(parties : {self.access_party_rules[(entity, action_type)]}).")
                    continue
                actors = ", ".join(sorted(authorized_actors))
                suggestion = f"'rule {entity}.{action_type} sharedBy {actors}'"
                extra = ""
                if allowed_shared:
                    uncovered = authorized_actors - allowed_shared
                    extra = (f" Une règle 'sharedBy' existe déjà pour '{key}' mais ne couvre pas : "
                             f"[{', '.join(sorted(uncovered))}].")
                raise ASTValidationError(
                    f"🔒 [CRITICAL_COLLISION] Conflit d'autorité sur l'entité '{entity}' : "
                    f"les acteurs [{actors}] ont tous le droit d'exécuter l'action '{action_type}'. "
                    f"Séparez ces privilèges, ou déclarez explicitement le partage avec : {suggestion}.{extra}"
                )

    def _valider_regle_apres_paiement(self):
        """Valide le canal d'écriture réservé qui contourne le CRUD verrouillé."""
        self.postpayment_writable = {}
        champs_vus = set()
        regles_serveur = (
            ("generated", self.generated_fields),
            ("derivedFrom", self.derived_fields),
            ("sumOf", self.aggregated_fields),
            ("timestamp", self.timestamp_fields),
            ("numbered", self.numbered_fields),
        )
        for rule in self.rules:
            if rule["type"] != "writableAfterPayment":
                continue
            reference = rule["reference"]
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' doit référencer "
                    f"'Entite.champ', reçu '{reference}'.")
            entity, field = reference.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' cible l'entité "
                    f"'{entity}' qui n'existe pas.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' cible le champ "
                    f"'{entity}.{field}', qui n'est pas un attribut déclaré.")
            if not any(pf["entity"] == entity for pf in self.payable_fields):
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' ne vaut que sur "
                    f"une entité 'payable' — '{entity}' ne l'est pas.")
            actor = rule["value"]
            if actor not in self.actors:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' sur "
                    f"'{entity}.{field}' nomme l'acteur '{actor}', qui n'est pas "
                    f"un acteur déclaré.")
            for type_regle, champs in regles_serveur:
                if any(c["entity"] == entity and c["field"] == field
                       for c in champs):
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est à la fois "
                        f"'writableAfterPayment' et '{type_regle}' — incompatible : "
                        f"'{type_regle}' interdit toute écriture cliente.")
            proprietaire = self.transitive_ownership.get(entity, {}).get("actor")
            if proprietaire is None:
                proprietaires_directs = {
                    owner for (owned_entity, _action), owner
                    in self.ownership_rules.items()
                    if owned_entity == entity and owner in self.actors
                }
                if len(proprietaires_directs) == 1:
                    proprietaire = next(iter(proprietaires_directs))
            if proprietaire == actor:
                raise ASTValidationError(
                    f"Structure : la règle 'writableAfterPayment' sur "
                    f"'{entity}.{field}' nomme '{actor}', qui est déjà propriétaire "
                    f"de '{entity}' — le verrou de paiement serait contournable par "
                    f"son propriétaire.")
            config = self.postpayment_writable.get(entity)
            if config and config["actor"] != actor:
                raise ASTValidationError(
                    f"Structure : deux acteurs différents sont déclarés "
                    f"'writableAfterPayment' sur '{entity}' : "
                    f"'{config['actor']}' et '{actor}' — un seul acteur autorisé.")
            if (entity, field) in champs_vus:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'writableAfterPayment' déclarées "
                    f"pour '{entity}.{field}' — une seule autorisée.")
            champs_vus.add((entity, field))
            if config is None:
                config = {"actor": actor, "fields": []}
                self.postpayment_writable[entity] = config
            config["fields"].append(field)

    def _audit_security_rules(self):
        """Moteur d'analyse statique traquant les vulnérabilités complexes."""
        reports = []
        restricted_fields = {}

        for rule in self.rules:
            if rule["type"] == "restrictedTo":
                restricted_fields[rule["reference"]] = rule["value"]

        custom_callers = {}
        for wf in self.workflows:
            actor = wf["actor"]
            for action in wf["actions"]:
                target = action["target"]
                if action["type"] == "Delete" and actor != "Admin":
                    reports.append(f"⚠️  [CRITICAL_WARNING] Le workflow '{wf['name']}' permet à l'acteur '{actor}' de supprimer l'entité '{target}'. Assurez-vous que cette action est hautement sécurisée au niveau infra.")

                if action["type"] == "Execute":
                    if target not in custom_callers:
                        custom_callers[target] = set()
                    custom_callers[target].add(actor)

        for c_name, c_bloc in self.custom_logic.items():
            inputs = c_bloc.get("input", [])
            calling_actors = custom_callers.get(c_name, set())

            for inp in inputs:
                if "reference" in inp:
                    ref = inp["reference"]
                    if ref in restricted_fields:
                        allowed_actor = restricted_fields[ref]
                        for caller in calling_actors:
                            if caller != allowed_actor:
                                reports.append(f"🔒 [SECURITY_AUDIT] Le bloc de logique IA '{c_name}' (exécuté par '{caller}') utilise la donnée sensible '{ref}' restreinte à l'acteur '{allowed_actor}'.")

        if not reports:
            print("🛡️  Audit : Aucune vulnérabilité ou privilège excessif détecté dans la spécification.")
        else:
            print(f"🛑 Audit : {len(reports)} point(s) de vigilance sécurité identifié(s) :")
            for r in reports:
                print(f"   {r}")

        return reports

    def to_normalized_ast(self, security_reports: list[str]) -> CompilationIR:
        normalized: CompilationIR = {
            "meta": {"appName": self.app_name, "security_audit_logs": security_reports},
            "schema": {"entities": self.entities, "relations": self.relations},
            "security": {
                "actors": list(self.actors),
                "self_register_actors": list(self.self_register_actors),
                "rules": self.rules, "workflows": self.workflows,
                "ownership": {f"{k[0]}.{k[1]}": v for k, v in self.ownership_rules.items()},
                "transitive_ownership": self.transitive_ownership,
                "access_parties": {f"{k[0]}.{k[1]}": v for k, v in self.access_party_rules.items()},
                # AJOUT (brique 23) : rôles superviseurs qui transpercent le
                # contrôle 'accessibleBy' — item par item, même clé.
                "access_supervisors": {f"{k[0]}.{k[1]}": v for k, v in self.access_supervisors.items()},
                "public": [f"{e}.{a}" for e, a in sorted(self.public_actions)],
                "public_conditions": {
                    f"{e}.{a}": value
                    for (e, a), value in sorted(self.public_conditions.items())
                },
                "once_per": list(self.once_per_rules),
                "hidden_fields": [f"{e}.{f}" for e, f in sorted(self.masked_fields)],
                "reputation_rules": self.reputation_rules,
                "categorized_fields": self.categorized_fields,
                "generated_fields": self.generated_fields,
                "timestamp_fields": self.timestamp_fields,
                "numbered_fields": self.numbered_fields,
                "required_profiles": self.required_profiles,
                "payable_fields": self.payable_fields,
                "writable_after_payment": self.postpayment_writable,
                "derived_fields": self.derived_fields,
                "aggregated_fields": self.aggregated_fields,
                # POINT 85 : {(entite, champ): {"required"|"unique": True,
                #             "min"|"max": {"portee", "valeur"}}}. Les clés sont
                # des tuples : le générateur les indexe, rien ne les sérialise.
                "field_constraints": self.field_constraints,
                # POINT 95 : formes acceptées pour l'identifiant de compte, ou
                # None si la spec n'en déclare aucune (comportement historique).
                "auth_identifier": self.auth_identifier,
                # POINT 95 : indicatif qui rend '06…' et '+336…' canoniques.
                # Déclaré, jamais deviné : monl ignore d'où appelle l'usager.
                "auth_phone_prefix": self.auth_phone_prefix,
                # BRIQUE 19 (point 96) : {Entite: {champ: [valeurs]}}.
                "enumerated_fields": self.enumerated_fields,
                # BRIQUE B3 : capacités de liste déclarées une par une. Ces
                # listes sont la whitelist de compilation consommée par le
                # générateur ; le client ne peut donc ni inventer une colonne
                # ni un opérateur.
                "filterable_fields": self.filterable_fields,
                "sortable_fields": self.sortable_fields,
                # BRIQUE 20 (point 98) : [{entity, field, value, releases}] —
                # atteindre la valeur rend ce que les enfants ont consommé.
                "release_rules": self.release_rules,
                "upload_fields": self.upload_fields,
                "message_rules": self.message_rules,
                # BRIQUE B4 : configuration d'authentification, vide quand la
                # spec ne demande aucune capacité nouvelle.
                "auth_features": self.auth_features,
                "payment_currency": self.payment_currency,
                "payment_provider": self.payment_provider,
            },
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())},
            "ui": self.ui_overrides,
            "landing": self.landing,
            "capabilities": self.capabilities,
            "seeds": self.seeds,
            "assets": self.assets,
            "migrations": self.migrations,
        }
        return normalized
