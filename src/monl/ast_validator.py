import os
import re

# Dossier par défaut des assets fournis par l'humain (brique 13, point 83).
# HORS de frontend/ : ce dossier-là est renommé par 'monl frontend' à chaque
# construction, et sa liste blanche n'accepte pas les .jpg -- les photos qu'on y
# déposait finissaient donc dans frontend.precedent/ sans un mot.
DEFAULT_ASSETS_DIR = "assets"


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


class ASTValidationError(Exception):
    pass

class MonlAST:
    def __init__(self, raw_json, base_dir=None):
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
        self.ui_overrides_raw = raw_json.get("ui_overrides", [])
        self.landing_raw = raw_json.get("landing")
        self.capabilities_raw = raw_json.get("capabilities", [])
        self.seeds_raw = raw_json.get("seeds", [])
        self.assets_raw = raw_json.get("assets") or {}
        self.assets = {}
        self.public_actions = set()

        for ent in raw_json.get("entities", []):
            name = ent["name"]
            attrs = {attr["name"]: attr["type"] for attr in ent["attributes"]}
            self.entities[name] = attrs

    def validate_and_audit(self):
        """Exécute la validation de cohérence et l'analyse statique de sécurité."""
        print(f"🔬 Analyse statique et audit de sécurité pour '{self.app_name}'...")

        # 1. Validations structurelles obligatoires
        self._validate_structures()

        # 2. Audit de sécurité actif
        security_reports = self._audit_security_rules()

        # 3. AJOUT (bêta 3) : audit du périmètre d'inscription libre. Un rôle
        #    non marqué 'selfRegister' ne peut pas être choisi par un client à
        #    l'inscription — c'est ce qui empêche l'élévation de privilège par
        #    simple création de compte. On le rend visible à la compilation :
        #    silence = personne ne s'inscrit, ce qui est sûr mais rarement
        #    voulu ; rôle privilégié ouvert = choix explicite, tracé ici.
        security_reports.extend(self._audit_self_registration())

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

    def _validate_structures(self):
        """Vérifie la cohérence de base et traque les collisions multi-acteurs (Bug #5),
        sauf exemption explicite via une règle 'sharedBy'. Valide aussi les règles
        'ownedBy' (roadmap : contrôle d'accès par propriété)."""
        # Matrice globale pour traquer les conflits d'autorisations (Entité -> Action -> Ensemble d'acteurs)
        access_matrix = {}

        # CORRECTIF (post-v6) : les règles 'sharedBy' déclarent explicitement qu'un
        # ensemble précis d'acteurs peut se partager un même droit d'écriture sur
        # une entité, ex. : "rule Post.Delete sharedBy Admin, Moderator"
        shared_permissions = {}
        for rule in self.rules:
            if rule["type"] == "sharedBy":
                shared_permissions[rule["reference"]] = set(rule["value"])

        self._valider_contraintes_de_champ()

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

            # L'intermédiaire doit lui-même déclarer un propriétaire : c'est le
            # seul maillon qui relie la chaîne à un compte.
            maillons = proprietaires_par_entite.get(owner_entity, set())
            if not maillons:
                raise ASTValidationError(
                    f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' désigne "
                    f"'{owner_entity}' comme propriétaire, mais '{owner_entity}' n'est ni un acteur, "
                    f"ni possédé lui-même -- la chaîne ne remonte à aucun compte, donc le serveur ne "
                    f"peut vérifier À QUI appartient un '{entity}'. Ajouter une règle "
                    f"'{owner_entity}.Read ownedBy <Acteur>', ou rattacher '{entity}' directement à "
                    f"un acteur."
                )
            if len(maillons) > 1:
                raise ASTValidationError(
                    f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' passe par "
                    f"'{owner_entity}', qui déclare plusieurs propriétaires différents "
                    f"({', '.join(sorted(maillons))}) -- la chaîne est ambiguë : le serveur ne saurait "
                    f"pas lequel vérifier. N'en désigner qu'un seul sur '{owner_entity}'."
                )
            acteur = next(iter(maillons))
            # Une seule indirection pour l'instant : la jointure générée est à
            # un seul niveau. Deux niveaux compileraient en filtrant sur le
            # mauvais maillon -- c'est exactement la classe de défaut que le
            # point 80 a fermée, on ne la rouvre pas par la profondeur.
            if acteur not in self.actors:
                raise ASTValidationError(
                    f"Structure : la règle 'ownedBy' sur '{entity}.{act_type}' formerait une chaîne de "
                    f"propriété à plus d'un niveau ('{entity}' -> '{owner_entity}' -> '{acteur}', qui "
                    f"n'est toujours pas un acteur). monl ne sait remonter qu'UN intermédiaire : "
                    f"rattacher '{entity}' à '{acteur}' directement, ou à un acteur."
                )
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
            self.transitive_ownership[entity] = {"via": owner_entity, "actor": acteur}

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

        # AJOUT (roadmap, écosystème de capacités -- brique 2) : validation
        # des règles 'hidden' -- retire un champ de toutes les réponses de
        # lecture de son entité (voir le commentaire de grammaire dans
        # parser.py pour la distinction avec 'restrictedTo'). Vérifie que le
        # champ référencé est un attribut réellement déclaré sur l'entité
        # (donc jamais 'id', qui n'apparaît pas dans self.entities -- un
        # champ structurellement nécessaire à la navigation CRUD ne peut pas
        # être masqué, la règle échoue proprement plutôt que de casser
        # silencieusement les routes Update/Delete/Read-par-ID).
        self.masked_fields = set()
        for rule in self.rules:
            if rule["type"] == "hidden":
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

        # AJOUT (roadmap, écosystème de capacités -- brique 5) : validation
        # des règles 'categorized' -- remplace un champ Integer/Float par un
        # libellé de catégorie (ex. "peu"/"populaire"/"viral") dans toutes
        # les réponses de lecture, sur le même principe que 'hidden' mais en
        # substituant une donnée dérivée plutôt qu'en supprimant purement.
        self.categorized_fields = []
        _categorized_seen_fields = set()
        for rule in self.rules:
            if rule["type"] == "categorized":
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
                # Incompatible avec 'hidden' sur le même champ : 'hidden' retire
                # le champ, 'categorized' le remplace par une valeur dérivée --
                # les deux ne peuvent pas s'appliquer en même temps sans que
                # l'un des deux comportements soit silencieusement ignoré.
                if (entity, field) in self.masked_fields:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'categorized' -- incompatible : "
                        f"'hidden' retire le champ, 'categorized' le remplace par une catégorie dérivée de sa valeur."
                    )
                if (entity, field) in _categorized_seen_fields:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'categorized' déclarées pour '{entity}.{field}' -- une seule autorisée."
                    )
                _categorized_seen_fields.add((entity, field))

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
                thresholds = [c["below"] for c in clauses[:-1]]
                if thresholds != sorted(set(thresholds)) or len(thresholds) != len(set(thresholds)):
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' -- les seuils 'below' doivent être "
                        f"strictement croissants (reçu : {thresholds})."
                    )
                if any(not c["label"].strip() for c in clauses):
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' -- chaque palier doit avoir un libellé non vide."
                    )
                self.categorized_fields.append({"entity": entity, "field": field, "clauses": clauses})

        # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
        # validation des règles 'generated' -- retire un champ String du
        # corps de requête Create attendu, peuplé côté serveur par le
        # pseudonyme anonyme stable du compte courant (voir /register et
        # /login dans generator.py) plutôt que fourni par le client.
        self.generated_fields = []
        _generated_seen_fields = set()
        for rule in self.rules:
            if rule["type"] == "generated":
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
                # Incompatible avec 'hidden' sur le même champ : 'generated'
                # existe précisément pour produire une valeur sûre à
                # afficher (un pseudonyme, jamais l'identité réelle) -- la
                # masquer entièrement en plus n'aurait aucun sens, ce serait
                # alors juste ne pas déclarer le champ du tout.
                if (entity, field) in self.masked_fields:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'generated' -- incompatible : "
                        f"'generated' produit déjà une valeur sûre à afficher, la masquer en plus n'a pas de sens."
                    )
                if (entity, field) in _generated_seen_fields:
                    raise ASTValidationError(
                        f"Structure : plusieurs règles 'generated' déclarées pour '{entity}.{field}' -- une seule autorisée."
                    )
                _generated_seen_fields.add((entity, field))
                # Incompatible avec une action 'Create' 'public' sur la même
                # entité : 'generated' peuple le champ depuis l'identité de
                # l'appelant authentifié -- une route publique n'a par
                # définition aucune identité fiable à partir de laquelle
                # dériver un pseudonyme.
                if (entity, "Create") in self.public_actions:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est 'generated', mais '{entity}.Create' est 'public' -- "
                        f"incompatible : 'generated' exige un appelant authentifié dont dériver le pseudonyme."
                    )
                self.generated_fields.append({"entity": entity, "field": field})

        # AJOUT (roadmap, écosystème de capacités -- brique 16, point 89) :
        # validation de 'timestamp'. Le champ porte l'instant de CRÉATION,
        # écrit par le serveur et jamais ensuite : même famille que
        # 'generated' et 'derivedFrom', donc mêmes conséquences (absent du
        # schéma d'entrée, absent du SET de la route Update).
        self.timestamp_fields = []
        _timestamp_seen = set()
        for rule in self.rules:
            if rule["type"] != "timestamp":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'timestamp' doit référencer 'Entite.champ', "
                    f"reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'timestamp' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "DateTime":
                # 'Date' est refusé explicitement, et pas par simple omission :
                # le serveur CONNAÎT l'heure, la tronquer au jour perdrait de
                # l'information sans que personne ne le demande -- et rendrait
                # deux enregistrements du même jour impossibles à ordonner, ce
                # qui est justement l'usage d'un horodatage.
                indice = (" -- 'Date' tronquerait l'heure que le serveur connaît, "
                          "et deux enregistrements du même jour ne seraient plus "
                          "ordonnables" if field_type == "Date" else "")
                raise ASTValidationError(
                    f"Structure : 'timestamp' cible le champ '{entity}.{field}', qui doit être "
                    f"un attribut DateTime déclaré (reçu : {field_type or 'champ inexistant'})"
                    f"{indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'timestamp' -- "
                    f"incompatible : le client ne peut pas l'écrire et ne pourrait pas le lire, "
                    f"donc ce champ n'existerait nulle part."
                )
            if (entity, field) in _timestamp_seen:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'timestamp' déclarées pour '{entity}.{field}' "
                    f"-- une seule autorisée."
                )
            if any(t["entity"] == entity for t in self.timestamp_fields):
                autre = next(t["field"] for t in self.timestamp_fields if t["entity"] == entity)
                raise ASTValidationError(
                    f"Structure : '{entity}' porte deux champs 'timestamp' ('{autre}' et "
                    f"'{field}') -- tous deux recevraient le MÊME instant de création. "
                    f"Un horodatage de modification serait une autre brique, pas celle-ci."
                )
            _timestamp_seen.add((entity, field))
            self.timestamp_fields.append({"entity": entity, "field": field})

        # AJOUT (brique 22, point 102) : validation de 'numbered'. Le champ porte
        # un NUMÉRO LISIBLE attribué par le serveur — même famille que
        # 'timestamp' juste au-dessus, et mêmes conséquences.
        self.numbered_fields = []
        for rule in self.rules:
            if rule["type"] != "numbered":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'numbered' doit référencer 'Entite.champ', "
                    f"reçu '{rule['reference']}'.")
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'numbered' cible l'entité '{entity}' qui "
                    f"n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                # 'UUID' est refusé en le NOMMANT : c'est le type qu'on est
                # tenté de choisir pour une référence, et depuis le point 101 il
                # vérifie sa forme — un numéro lisible n'y entrerait jamais.
                indice = (" -- un 'UUID' vérifie sa forme depuis le point 101, et "
                          "un numéro lisible n'en a pas la forme"
                          if field_type == "UUID" else "")
                raise ASTValidationError(
                    f"Structure : 'numbered' cible le champ '{entity}.{field}', qui doit "
                    f"être un attribut String déclaré (reçu : "
                    f"{field_type or 'champ inexistant'}){indice}.")
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et "
                    f"'numbered' -- incompatible : le client ne peut pas l'écrire et ne "
                    f"pourrait pas le lire, donc ce numéro n'existerait pour personne.")
            if any(n["entity"] == entity and n["field"] == field
                   for n in self.numbered_fields):
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'numbered' déclarées pour "
                    f"'{entity}.{field}' -- une seule autorisée.")
            self._valider_gabarit_de_numero(entity, field, rule["value"])
            self.numbered_fields.append({
                "entity": entity, "field": field, "format": rule["value"],
                "periode": self._periode_du_gabarit(rule["value"]),
            })

        # AJOUT (brique 19, point 96) : validation de 'oneOf'. Un statut n'est
        # pas du texte, c'est un état parmi quelques-uns — et sur une commande
        # NON réglée, le client posait `status: "livrée"` et le serveur
        # l'acceptait (constaté sur `projets/SneakerLab`).
        self.enumerated_fields = {}
        for rule in self.rules:
            if rule["type"] != "oneOf":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'oneOf' doit référencer 'Entite.champ', "
                    f"reçu '{rule['reference']}'.")
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'oneOf' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            # Volontairement restreint aux types TEXTE. Une valeur parmi une
            # liste de nombres se dirait 'min'/'max' (point 85) ou
            # 'categorized' (brique 5) ; ouvrir 'oneOf' aux nombres ferait trois
            # façons d'exprimer la même contrainte, dont deux se contrediraient.
            if field_type not in ("String", "Text"):
                raise ASTValidationError(
                    f"Structure : 'oneOf' cible '{entity}.{field}', qui doit être un "
                    f"champ String ou Text (reçu : {field_type or 'champ inexistant'}) — "
                    f"pour un nombre, 'min'/'max' ou 'categorized' disent déjà cela.")
            valeurs = rule["value"]
            if len(valeurs) < 2:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' n'énumère qu'une valeur — "
                    f"un champ qui n'a qu'une valeur possible n'a pas besoin d'être saisi.")
            vides = [v for v in valeurs if not v.strip()]
            if vides:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' contient une valeur vide — "
                    f"elle serait indistinguable d'un champ non rempli à l'écran.")
            doublons = [v for v in set(valeurs) if valeurs.count(v) > 1]
            if doublons:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' répète "
                    f"{', '.join(repr(d) for d in sorted(doublons))} — une liste de choix "
                    f"qui propose deux fois la même chose est une erreur de saisie.")
            if entity in self.enumerated_fields and field in self.enumerated_fields[entity]:
                raise ASTValidationError(
                    f"Structure : deux règles 'oneOf' sur '{entity}.{field}' — laquelle "
                    f"des deux listes s'appliquerait ?")
            # Un champ que le SERVEUR peuple ne se choisit pas : la liste ne
            # serait jamais consultée, et l'écran proposerait un menu inerte.
            if any(g["entity"] == entity and g["field"] == field
                   for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'oneOf' — "
                    f"le serveur l'écrit lui-même, la liste de choix ne serait jamais lue.")
            self.enumerated_fields.setdefault(entity, {})[field] = list(valeurs)


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

        # AJOUT (roadmap, écosystème de capacités -- brique 10, point 77) :
        # validation de 'derivedFrom'. La règle nomme un champ CALCULÉ PAR LE
        # SERVEUR depuis une ligne liée. Elle existe parce que `payable`
        # relisait en base un montant que le client y avait écrit -- vrai à la
        # création comme à la modification, deux exploits prouvés. Les refus
        # ci-dessous sont le cœur de la brique : un calcul mal déclaré doit
        # échouer à la compilation, jamais donner un montant faux à encaisser.
        self.derived_fields = []
        for rule in self.rules:
            if rule["type"] != "derivedFrom":
                continue
            reference, source_ref = rule["reference"], rule["value"]
            facteur = rule["factor"]
            if "." not in reference or "." not in source_ref:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' doit référencer 'Entite.champ derivedFrom Entite.champ by champ', "
                    f"reçu '{reference} derivedFrom {source_ref}'."
                )
            entity, field = reference.split(".", 1)
            source_entity, source_field = source_ref.split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' cible l'entité '{entity}' qui n'existe pas."
                )
            if source_entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit l'entité '{source_entity}' qui n'existe pas."
                )
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
            # Le multiplicateur vit sur l'entité calculée et doit être fourni :
            # sans 'required', un client qui l'omet donnerait 'NULL x prix'.
            facteur_type = self.entities[entity].get(facteur)
            if facteur_type != "Integer":
                raise ASTValidationError(
                    f"Structure : 'derivedFrom ... by {facteur}' exige que '{entity}.{facteur}' soit un attribut "
                    f"Integer déclaré (reçu : {facteur_type or 'champ inexistant'}) -- on multiplie par une quantité."
                )
            champs_requis = {r["reference"] for r in self.rules
                             if r.get("type") == "required"}
            if f"{entity}.{facteur}" not in champs_requis:
                raise ASTValidationError(
                    f"Structure : '{entity}.{facteur}' sert de multiplicateur à 'derivedFrom' et doit donc porter "
                    f"'rule {entity}.{facteur} required' -- sinon un client qui l'omet ferait calculer sur du vide."
                )
            if facteur == field:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' ne peut pas être son propre multiplicateur."
                )
            # Un montant calculé mais masqué serait invérifiable par celui qui
            # le règle -- même raison que pour 'payable' (point 74).
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'derivedFrom' -- incompatible : "
                    f"un montant calculé qu'on ne peut pas lire ne peut pas être vérifié."
                )
            if any(g["entity"] == entity and g["field"] == field
                   for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'derivedFrom' -- deux façons "
                    f"concurrentes de le peupler côté serveur, il faut choisir."
                )
            if any(d["entity"] == entity and d["field"] == field
                   for d in self.derived_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte plusieurs règles 'derivedFrom' -- un seul calcul par champ."
                )
            # Il faut une relation qui donne à l'entité calculée une clé
            # étrangère vers la source : c'est elle qui dit QUELLE ligne lire.
            # Même vérification que pour 'increments' (point 27), répliquée
            # plutôt que partagée -- la brique est trop jeune pour factoriser.
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
            # La source ne peut pas être le propriétaire : la clé étrangère du
            # propriétaire est peuplée depuis le JWT, jamais choisie par le
            # client. Si '{source_entity}' possédait '{entity}', le client
            # n'aurait aucun moyen de désigner la ligne à lire.
            proprietaires = {v for (ent, _act), v in self.ownership_rules.items()
                             if ent == entity}
            if proprietaires and source_entity in proprietaires:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' lit '{source_entity}', qui est aussi le propriétaire de "
                    f"'{entity}' (règle 'ownedBy') -- sa clé étrangère vient du jeton, pas du client, donc "
                    f"aucune ligne de '{source_entity}' ne peut être désignée à la création."
                )
            if not proprietaires:
                raise ASTValidationError(
                    f"Structure : 'derivedFrom' sur '{entity}.{field}' exige que '{entity}' ait un propriétaire "
                    f"(une règle 'ownedBy') -- c'est lui qui distingue la clé étrangère peuplée par le serveur "
                    f"de celle que le client fournit pour désigner la ligne à lire."
                )
            self.derived_fields.append({
                "entity": entity, "field": field,
                "source_entity": source_entity, "source_field": source_field,
                "factor": facteur,
            })

        # AJOUT (roadmap, écosystème de capacités -- brique 12, point 82) :
        # validation de 'sumOf'. `derivedFrom` ne sait lire qu'UNE ligne liée ;
        # une commande à plusieurs articles a besoin de la SOMME de ses lignes.
        # C'est la troisième et dernière brique du panier cadrée au point 80.
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
                raise ASTValidationError(
                    f"Structure : 'sumOf' cible l'entité '{entity}' qui n'existe pas."
                )
            if source_entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'sumOf' additionne l'entité '{source_entity}' qui n'existe pas."
                )
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
                    f"attribut Money, Float ou Integer déclaré "
                    f"(reçu : {source_type or 'champ inexistant'})."
                )
            if source_entity == entity:
                raise ASTValidationError(
                    f"Structure : 'sumOf' fait de '{entity}.{field}' la somme d'un champ de "
                    f"'{entity}' lui-même -- une entité ne peut pas s'additionner. La somme porte "
                    f"sur une entité ENFANT (ex. 'Commande hasMany Ligne')."
                )
            # Sans relation parent → enfant, il n'y a pas de colonne qui dise
            # QUELLES lignes additionner : la somme porterait sur toute la table.
            a_relation_enfant = any(
                (rel["type"] in ("hasMany", "hasOne")
                 and rel["source"] == entity and rel["target"] == source_entity)
                or (rel["type"] == "belongsTo"
                    and rel["source"] == source_entity and rel["target"] == entity)
                for rel in self.relations
            )
            if not a_relation_enfant:
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
            if any(g["entity"] == entity and g["field"] == field
                   for g in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'sumOf' -- deux façons "
                    f"concurrentes de le peupler côté serveur, il faut choisir."
                )
            if any(d["entity"] == entity and d["field"] == field
                   for d in self.derived_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte à la fois 'derivedFrom' et 'sumOf' -- deux "
                    f"calculs concurrents pour un seul champ. 'derivedFrom' lit UNE ligne liée, 'sumOf' "
                    f"additionne des enfants : choisir lequel."
                )
            if any(a["entity"] == entity and a["field"] == field
                   for a in self.aggregated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' porte plusieurs règles 'sumOf' -- une seule somme "
                    f"par champ."
                )
            # Même exigence que 'derivedFrom', et pour la même raison : c'est le
            # propriétaire déclaré qui distingue la clé étrangère peuplée par le
            # serveur depuis le jeton de celle que le client fournit. Sans lui,
            # la colonne qui relie la ligne à sa commande pourrait recevoir un id
            # de COMPTE (voir _identity_fk_columns), et la somme se recalculerait
            # sur le mauvais parent. Une ligne sans propriétaire serait de toute
            # façon créable par n'importe qui, donc le total d'un tiers
            # déplaçable à volonté -- ce qui le rendrait inencaissable.
            proprietaires_source = {v for (ent, _act), v in self.ownership_rules.items()
                                    if ent == source_entity}
            if not proprietaires_source:
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

        # AJOUT (point 79) : recoupement des deux briques, et le refus qui rend
        # STRUCTURELLE la garantie du point 74. Il vient après les deux boucles
        # parce qu'il a besoin des deux listes.
        #
        # Le raisonnement, en trois pas : la clé étrangère du propriétaire est
        # peuplée avec `current_user_id` à la création, donc le CRÉATEUR d'un
        # enregistrement en est toujours le propriétaire ; la route de règlement
        # oppose un 403 à quiconque n'est pas le propriétaire, donc le
        # propriétaire est le PAYEUR ; par conséquent, si le montant figure dans
        # le corps de création, le payeur écrit lui-même ce qu'il paie.
        #
        # C'était le cas de toute boutique compilée jusqu'ici : deux exploits de
        # trois requêtes suffisaient à encaisser un centime pour 945 euros
        # (point 77). Le seul montant sûr est donc celui qu'aucun corps de
        # requête ne peut porter -- un champ 'derivedFrom' ou, depuis le
        # point 82, un champ 'sumOf' (le total d'un panier à plusieurs lignes).
        champs_derives = {(d["entity"], d["field"]) for d in self.derived_fields}
        champs_sommes = {(a["entity"], a["field"]): a for a in self.aggregated_fields}

        # POINT 85 : une borne 'min'/'max' vit dans le schéma Pydantic, donc dans
        # le corps de requête. Sur un champ que le SERVEUR peuple ('generated',
        # 'derivedFrom', 'sumOf'), ce champ n'est pas dans le schéma : la borne
        # n'aurait aucun endroit pour s'appliquer. Refuser plutôt que l'écrire
        # nulle part -- c'est la faute même que le point 85 corrige, et la
        # reproduire ici serait grotesque. Recoupement APRÈS les trois boucles,
        # comme le refus du point 79 : il lui faut leurs listes.
        peuples_par_le_serveur = (
            champs_derives
            | set(champs_sommes)
            | {(g["entity"], g["field"]) for g in self.generated_fields}
            # POINT 89 : un champ 'timestamp' rejoint la même famille. Le
            # rattacher ICI plutôt que d'écrire un refus à lui seul est tout
            # l'intérêt d'avoir groupé ce recoupement : la brique 16 hérite des
            # trois refus sans une ligne de plus.
            | {(t["entity"], t["field"]) for t in self.timestamp_fields}
            # POINT 102 : un champ 'numbered' rejoint la même famille, et hérite
            # des trois refus sans une ligne de plus — exactement ce que le
            # point 89 avait gagné à grouper ce recoupement.
            | {(n["entity"], n["field"]) for n in self.numbered_fields}
        )
        for (entite, champ), contraintes in sorted(self.field_constraints.items()):
            if (entite, champ) not in peuples_par_le_serveur:
                continue
            bornes = [n for n in ("min", "max") if n in contraintes]
            if bornes:
                raise ASTValidationError(
                    f"Structure : '{entite}.{champ}' porte "
                    f"'{'/'.join(bornes)}' alors que le SERVEUR calcule ce champ : il "
                    f"est absent du corps de requête, donc la borne ne s'appliquerait "
                    f"à rien. La retirer, ou borner le champ d'où la valeur vient.")
            # 'required' sur un champ que le client ne PEUT pas envoyer met le
            # contrat frontend en contradiction avec lui-même : « remplis-le »
            # d'un côté, « ne l'envoie pas » de l'autre. L'IA d'interface reçoit
            # alors deux consignes opposées sur le même champ.
            # 'unique', lui, reste permis : un pseudonyme 'generated' a toutes
            # les raisons d'être unique, et l'index s'applique en base sans rien
            # demander au client.
            if "required" in contraintes:
                raise ASTValidationError(
                    f"Structure : '{entite}.{champ}' est 'required' alors que le SERVEUR "
                    f"le calcule : le client ne peut pas le fournir, et le contrat "
                    f"dirait à la fois « à remplir » et « à ne pas envoyer ».")

        for payable in self.payable_fields:
            entity, field = payable["entity"], payable["field"]
            if (entity, field) not in champs_derives and (entity, field) not in champs_sommes:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'payable' mais le client peut l'écrire -- "
                    f"le créateur d'un '{entity}' en devient le propriétaire, donc le payeur : il "
                    f"fixerait lui-même ce qu'il règle. Ajouter une règle qui fait calculer le "
                    f"montant par le serveur, par exemple "
                    f"'rule {entity}.{field} derivedFrom Article.prix by quantite', ou "
                    f"'rule {entity}.{field} sumOf Ligne.sousTotal' pour un panier."
                )
            # AJOUT (point 82) : la faille du point 77 qui revenait par le
            # panier, et que le cadrage du point 80 annonçait.
            #
            # Un champ 'sumOf' est calculé par le serveur : il satisfait donc le
            # refus ci-dessus. Mais additionner un champ que le CLIENT écrit ne
            # produit pas un total sûr -- il produit un total que le client
            # contrôle, en une addition de plus. Le payeur reprend la main sur ce
            # qu'il règle, exactement comme au point 77 : la brique qui rend le
            # panier chiffrable aurait rouvert le trou que la précédente a fermé.
            #
            # Donc : ce qu'on somme pour encaisser doit être lui-même calculé par
            # le serveur. La contrainte vit ICI et non dans la boucle 'sumOf',
            # parce que sommer un champ client reste légitime hors paiement
            # (`Commande.nbArticles sumOf Ligne.quantite` compte des articles, il
            # n'encaisse rien) : c'est le cumul avec `payable` qui est fautif, pas
            # la somme.
            somme = champs_sommes.get((entity, field))
            if somme is not None:
                source = (somme["source_entity"], somme["source_field"])
                if source not in champs_derives and source not in champs_sommes:
                    raise ASTValidationError(
                        f"Structure : '{entity}.{field}' est 'payable' et somme "
                        f"'{somme['source_entity']}.{somme['source_field']}', que le client peut "
                        f"écrire -- additionner un montant fourni par le payeur donne un total que le "
                        f"payeur fixe encore, en une addition de plus. Faire calculer la ligne par le "
                        f"serveur, par exemple 'rule {somme['source_entity']}."
                        f"{somme['source_field']} derivedFrom Article.prix by quantite'."
                    )

        # AJOUT (roadmap, écosystème de capacités -- brique 3, généralisée en
        # brique 4) : validation des règles 'decrements'/'increments' --
        # même mécanique dans les deux sens (réputation qui baisse sur
        # signalement, compteur qui monte sur appréciation), donc une seule
        # boucle partagée, distinguée par 'direction'. Trois conditions :
        # (1) le déclencheur est bien 'Entite.Create' sur une entité
        # existante -- seule l'action 'Create' est prise en charge pour
        # l'instant, volontairement (une suppression ne "défait" pas l'effet,
        # ce serait une mécanique différente à concevoir à part) ; (2) la
        # cible est un champ Integer/Float réellement déclaré sur son
        # entité ; (3) une relation existe entre les deux entités permettant
        # de savoir quelle ligne de l'entité cible modifier (même
        # vérification que pour 'ownedBy', point 5 -- répliquée ici plutôt
        # que partagée, cette validation est encore trop jeune pour factoriser
        # sans risquer de rigidifier les deux prématurément).
        self.reputation_rules = []
        for rule in self.rules:
            if rule["type"] in ("decrements", "increments"):
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
                has_matching_relation = any(
                    (rel["type"] in ("hasMany", "hasOne") and rel["source"] == target_entity and rel["target"] == trigger_entity)
                    or (rel["type"] == "belongsTo" and rel["target"] == target_entity and rel["source"] == trigger_entity)
                    for rel in self.relations
                )
                if not has_matching_relation:
                    raise ASTValidationError(
                        f"Structure : '{direction}' sur '{trigger_entity}.Create' vers '{target_entity}.{target_field}' "
                        f"exige une relation entre les deux (ex. '{target_entity} hasMany {trigger_entity}'), absente ici."
                    )
                # BRIQUE 14 (point 86) : « by <champ> » retire ce que le client a
                # demandé, au lieu d'une constante. C'est ce qui manquait pour
                # décompter un stock — 'decrements' ne savait retirer que 1.
                champ_quantite = rule.get("amount_field")
                if champ_quantite:
                    type_quantite = self.entities[trigger_entity].get(champ_quantite)
                    if type_quantite != "Integer":
                        raise ASTValidationError(
                            f"Structure : '{direction} ... by {champ_quantite}' désigne un champ "
                            f"de '{trigger_entity}' qui doit être un Integer déclaré "
                            f"(reçu : {type_quantite or 'champ inexistant'}).")
                    # Même exigence que le multiplicateur de 'derivedFrom'
                    # (point 77) et pour la même raison : un champ que le client
                    # peut omettre ferait décompter sur du vide.
                    requis = {r["reference"] for r in self.rules
                              if r.get("type") == "required"}
                    if f"{trigger_entity}.{champ_quantite}" not in requis:
                        raise ASTValidationError(
                            f"Structure : '{trigger_entity}.{champ_quantite}' sert de quantité à "
                            f"'{direction}' : il lui faut 'rule {trigger_entity}.{champ_quantite} "
                            f"required', sinon un client qui l'omet ferait décompter sur du vide.")
                self.reputation_rules.append({
                    "trigger_entity": trigger_entity, "target_entity": target_entity,
                    "target_field": target_field, "amount": rule.get("amount"),
                    "amount_field": champ_quantite, "direction": direction,
                })

        # AJOUT (point 99) : encaisser exige un propriétaire qui soit un COMPTE.
        # Ce recoupement vit ici, après la boucle des décomptes, parce qu'il lui
        # faut `reputation_rules` complet — et il double le refus posé plus haut
        # avec les autres contrôles de 'payable', qui n'exigeait qu'une relation
        # entrante, N'IMPORTE laquelle.
        #
        # Ce que ça laissait passer : 'relation Produit hasMany Facture' suffisait
        # à compiler, et la route de règlement comparait `produit_id` à l'id du
        # compte appelant. La comparaison n'était juste que par accident — la
        # colonne recevait `current_user_id` faute de savoir faire autrement,
        # c'est-à-dire à cause du défaut que ce point corrige. Le rattachement
        # redevenu honnête, l'accident disparaît et le refus doit être écrit.
        #
        # Deux formes acceptées, et deux seulement : un parent ACTEUR (propriété
        # directe, la colonne porte un id de compte) ou une chaîne transitive
        # (point 87, la jointure rend ce même id de compte). La cible d'un
        # compteur est exclue même quand c'est un acteur : cette colonne-là est
        # choisie par le client, elle ne dit pas à qui la ligne appartient.
        for _paye in self.payable_fields:
            _entite = _paye["entity"]
            if _entite in self.transitive_ownership:
                continue
            _cibles = {r["target_entity"] for r in self.reputation_rules
                       if r["trigger_entity"] == _entite}
            _parents_acteurs = {
                (rel["source"] if rel["type"] in ("hasMany", "hasOne") else rel["target"])
                for rel in self.relations
                if (rel["type"] in ("hasMany", "hasOne") and rel["target"] == _entite)
                or (rel["type"] == "belongsTo" and rel["source"] == _entite)
            } & set(self.actors) - _cibles
            if not _parents_acteurs:
                raise ASTValidationError(
                    f"Structure : '{_entite}.{_paye['field']}' est 'payable', mais aucun "
                    f"ACTEUR ne possède un enregistrement de '{_entite}'. Une relation vers "
                    f"une table métier ne suffit pas : la colonne qu'elle produit porte "
                    f"l'id de cette ligne, pas celui d'un compte, et la route de règlement "
                    f"la compare à l'appelant. Déclarer 'un_acteur hasMany {_entite}', ou "
                    f"rattacher '{_entite}' à un acteur à travers son parent "
                    f"('rule {_entite}.Read ownedBy <Parent>')."
                )

        # AJOUT (brique 20, point 98) : atteindre une valeur DÉFAIT un effet.
        # Ce bloc vit APRÈS la boucle des décomptes, et pas au milieu des
        # autres règles : il lui faut `reputation_rules` complet pour vérifier
        # qu'il y a bien quelque chose à rendre. Même placement, et même
        # raison, que le recoupement `payable`/`derivedFrom` du point 79.
        # Annuler une commande la passait en « annulée » et gardait ses lignes :
        # le stock restait consommé. La restitution existait déjà (point 92),
        # mais seulement à la SUPPRESSION — ce qui efface l'historique.
        self.release_rules = []
        for rule in self.rules:
            if rule["type"] != "releases":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'releases' doit référencer 'Entite.champ', "
                    f"reçu '{rule['reference']}'.")
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'releases' cible l'entité '{entity}' qui "
                    f"n'existe pas.")
            # LE refus qui porte la brique. Sans 'oneOf', la valeur déclarée est
            # une chaîne libre : une faute de frappe donnerait une règle qui ne
            # se déclenche JAMAIS, sans que rien ne le dise. C'est exactement ce
            # que le point 85 refuse — une règle qui ne produit rien.
            choix = self.enumerated_fields.get(entity, {}).get(field)
            if not choix:
                raise ASTValidationError(
                    f"Structure : 'releases' exige que '{entity}.{field}' porte un "
                    f"'oneOf' — sans liste de valeurs, une faute de frappe donnerait "
                    f"une règle qui ne se déclenche jamais.")
            if rule["value"] not in choix:
                raise ASTValidationError(
                    f"Structure : 'releases' se déclenche sur la valeur "
                    f"{rule['value']!r}, absente du 'oneOf' de '{entity}.{field}' "
                    f"({', '.join(repr(c) for c in choix)}) — elle ne surviendrait "
                    f"jamais.")
            libere = rule["entity"]
            if libere not in self.entities:
                raise ASTValidationError(
                    f"Structure : 'releases' nomme l'entité '{libere}', qui n'existe pas.")
            # Ce qu'on libère, c'est un décompte : sans lui il n'y a rien à rendre.
            decomptes = [r for r in self.reputation_rules
                         if r["trigger_entity"] == libere
                         and r["direction"] == "decrements"]
            if not decomptes:
                raise ASTValidationError(
                    f"Structure : 'releases {libere}' ne libérerait rien — cette "
                    f"entité ne porte aucune règle 'decrements'. C'est ce qu'un "
                    f"décompte a consommé que l'on rend.")
            # Il faut savoir QUELLES lignes libérer : celles rattachées à
            # l'enregistrement dont le champ change. Sans relation, la question
            # n'a pas de réponse.
            if not any(r["source"] == entity and r["target"] == libere
                       for r in self.relations):
                raise ASTValidationError(
                    f"Structure : 'releases' exige une relation "
                    f"'{entity} hasMany {libere}' — sans elle, rien ne dit quelles "
                    f"lignes de {libere} dépendent de ce {entity}.")
            if any(r["entity"] == entity and r["field"] == field
                   for r in self.release_rules):
                raise ASTValidationError(
                    f"Structure : deux règles 'releases' sur '{entity}.{field}' — "
                    f"la première libération rendrait déjà le décompte, la seconde "
                    f"le rendrait une deuxième fois.")
            self.release_rules.append({"entity": entity, "field": field,
                                       "value": rule["value"], "releases": libere})

        # AJOUT (roadmap, contrôle du rendu visuel) : validation du bloc 'ui'
        # optionnel — vérifie que l'entité et les champs référencés existent
        # bien, pour éviter qu'une faute de frappe dans 'primary'/'order'
        # passe silencieusement inaperçue jusqu'au rendu du front. Le nom du
        # thème n'est volontairement pas validé ici (cosmétique, pas
        # sécuritaire) — un nom de thème inconnu sera simplement ignoré par
        # le générateur, qui retombera sur la sélection automatique.
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
                unknown = [f for f in order if f not in self.entities[entity]]
                if unknown:
                    raise ASTValidationError(
                        f"Structure : 'ui {entity}' référence des champs inconnus dans 'order' : {unknown}."
                    )
            self.ui_overrides[entity] = {
                "theme": override.get("theme"), "primary": primary, "order": order,
            }

        # PIVOT (point 41) : monl ne génère plus de landing — le bloc
        # 'landing' reste ACCEPTÉ pour ne casser aucune spec existante, mais
        # seul son 'brief' est conservé : il alimente désormais le contrat
        # frontend (FRONTEND_PROMPT.md) destiné à l'IA qui construit
        # l'interface. Les clés 'mode' et 'template', devenues sans effet,
        # sont signalées (jamais une régression silencieuse).
        self.landing = None
        if self.landing_raw is not None:
            for obsolete in ("mode", "template"):
                if self.landing_raw.get(obsolete):
                    print(f"⚠️  'landing / {obsolete}' est obsolète depuis le pivot "
                          f"(point 41 de docs/design_decisions.md) : monl ne génère "
                          f"plus de page d'accueil — seul 'brief' est transmis à l'IA frontend.")
            # AJOUT (point 55) : les sections éditoriales, seul contenu
            # statique que le contrat sache porter. Un titre vide donnerait
            # une rubrique sans nom dans l'interface : refusé à la
            # compilation plutôt que découvert à l'écran.
            sections = []
            for section in self.landing_raw.get("sections") or []:
                titre = (section.get("title") or "").strip()
                corps = (section.get("body") or "").strip()
                if not titre or not corps:
                    raise ValueError(
                        "SEMANTIC_ERROR: une 'section' de 'landing' exige un "
                        "titre ET un texte non vides (trouvé : "
                        f"titre={titre!r}, texte={corps!r}).")
                sections.append({"title": titre, "body": corps})
            # AJOUT (point 94) : la FAQ. Même exigence que les sections, pour la
            # même raison — une question sans réponse, ou une réponse sans
            # question, donnerait une entrée muette à l'écran. Le refus tombe à
            # la compilation, pas devant le visiteur.
            faq = []
            for entree in self.landing_raw.get("faq") or []:
                question = (entree.get("question") or "").strip()
                reponse = (entree.get("answer") or "").strip()
                if not question or not reponse:
                    raise ValueError(
                        "SEMANTIC_ERROR: une 'question' de 'landing' exige une "
                        "question ET une réponse non vides (trouvé : "
                        f"question={question!r}, réponse={reponse!r}).")
                faq.append({"question": question, "answer": reponse})
            self.landing = {"brief": self.landing_raw.get("brief"),
                            "sections": sections, "faq": faq}
        # AJOUT (roadmap, écosystème de capacités -- brique 1) : validation
        # du bloc optionnel 'capability'. Volontairement strict (liste
        # blanche de noms connus, contrairement à 'ui / theme' qui retombe
        # silencieusement sur un défaut) : une capacité mal orthographiée
        # doit être signalée à la compilation, pas ignorée en silence --
        # comportement déjà établi pour tout ce qui touche à la sécurité
        # (collision de privilèges, restriction de champ) dans ce compilateur.
        # 'auth' est la seule capacité connue pour l'instant (brique 1,
        # purement déclarative -- aucun effet sur la génération à ce stade).
        KNOWN_CAPABILITIES = {"auth", "payment"}
        # POINT 95 : une capacité est désormais un dict {name, …options}. Le nom
        # seul reste ce qui voyage dans l'AST normalisé (aucun consommateur
        # existant ne doit changer) ; les options sont extraites à part.
        noms = [c["name"] for c in self.capabilities_raw]
        unknown = [c for c in noms if c not in KNOWN_CAPABILITIES]
        if unknown:
            raise ASTValidationError(
                f"Structure : capacité(s) inconnue(s) déclarée(s) avec 'capability' : {', '.join(unknown)}. "
                f"Capacités reconnues : {', '.join(sorted(KNOWN_CAPABILITIES))}."
            )
        self.capabilities = list(dict.fromkeys(noms))  # dédoublonne, garde l'ordre
        self.auth_identifier = self._valider_identifiant_de_compte(
            self.capabilities_raw)

        # AJOUT (roadmap frontend, bloc 'seed') : validation des données de
        # démonstration. Chaque enregistrement doit cibler une entité
        # déclarée, ne référencer que des champs existants de cette entité,
        # et respecter grossièrement leur type (nombre pour Integer/Float/
        # Money, chaîne sinon). Strict comme le reste du compilateur : une
        # coquille dans un seed doit échouer à la compilation, pas produire
        # une INSERT invalide au démarrage du serveur.
        # AJOUT (roadmap, brique 13 -- point 83) : les ASSETS. monl ne savait pas
        # qu'un fichier existe : `imageUrl: "images/absent.jpg"` compilait sans
        # un mot, et l'image cassée ne se voyait qu'à l'œil, en ligne. Trois
        # chemins fautifs ont été essayés (fichier absent, dossier et extension
        # mal tapés, "/etc/passwd") : tous les trois compilaient.
        #
        # Deux familles de contrôles, séparées à dessein :
        #   - de FORME (toujours) : chemin absolu, remontée '..', URL distante ;
        #   - d'EXISTENCE (si base_dir est connu) : le fichier est-il là ?
        self.assets = dict(self.assets_raw)
        dossier_assets = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        self._verifier_forme_chemin_asset(dossier_assets, "assets.dir")
        self.assets["dir"] = dossier_assets
        for cle in ("logo", "favicon"):
            if cle not in self.assets_raw:
                continue
            valeur = self.assets_raw[cle]
            self._verifier_forme_chemin_asset(valeur, f"assets.{cle}")
            self._verifier_asset_present(valeur, f"assets.{cle}")

        NUMERIC_TYPES = {"Integer", "Float", "Money"}
        self.seeds = []
        for seed in self.seeds_raw:
            entity = seed["entity"]
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : le bloc 'seed' cible l'entité '{entity}' qui n'existe pas."
                )
            entity_fields = self.entities[entity]
            if seed.get("parent"):
                self._valider_parent_de_seed(entity, seed["parent"])
            for i, row in enumerate(seed["rows"], start=1):
                for field, value in row.items():
                    if field not in entity_fields:
                        raise ASTValidationError(
                            f"Structure : le bloc 'seed {entity}' (ligne {i}) référence le champ "
                            f"'{field}', qui n'est pas déclaré sur '{entity}'."
                        )
                    declared_type = entity_fields[field]
                    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
                    if declared_type in NUMERIC_TYPES and not is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {i}), champ '{field}' de type "
                            f"{declared_type} attend un nombre, reçu une chaîne."
                        )
                    if declared_type not in NUMERIC_TYPES and is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {i}), champ '{field}' de type "
                            f"{declared_type} attend une chaîne entre guillemets, reçu un nombre."
                        )
                    # Brique 13 : un champ 'Image' désigne un fichier LOCAL. Le
                    # vérifier ici, c'est transformer « image cassée en ligne,
                    # visible à l'œil » en « échec de compilation, nommé ».
                    if declared_type == "Image":
                        ou = f"seed {entity} (ligne {i}), champ '{field}'"
                        self._verifier_forme_chemin_asset(value, ou, image=True)
                        self._verifier_asset_present(value, ou)
            self.seeds.append(seed)

        for wf in self.workflows:
            actor = wf["actor"]
            if actor not in self.actors:
                raise ASTValidationError(f"Structure : L'acteur '{actor}' dans le workflow '{wf['name']}' n'est pas déclaré.")

            for action in wf["actions"]:
                target = action["target"]
                act_type = action["type"]

                if act_type == "Execute":
                    if target not in self.custom_logic:
                        raise ASTValidationError(f"Architecture : L'action Execute appelle '{target}', mais ce bloc custom n'est pas défini.")
                else:
                    base_target = target.split(".")[0] if "." in target else target
                    if base_target not in self.entities:
                        raise ASTValidationError(f"Structure : L'action cible l'entité '{base_target}' qui n'existe pas.")

                    # --- CORRECTIF BUG v6 #5 : Détection des collisions de privilèges ---
                    # AJOUT (roadmap, public) : une action marquée 'public' ne
                    # vérifie plus aucune identité au runtime — peu importe
                    # combien de workflows/acteurs différents la déclarent,
                    # ça n'a plus de sens de la faire remonter dans la
                    # matrice de collision, qui ne concerne que les actions
                    # réellement soumises à un contrôle de rôle.
                    if (base_target, act_type) in self.public_actions:
                        continue

                    if base_target not in access_matrix:
                        access_matrix[base_target] = {}
                    if act_type not in access_matrix[base_target]:
                        access_matrix[base_target][act_type] = set()

                    # Enregistrement de l'acteur pour cette action précise
                    access_matrix[base_target][act_type].add(actor)

        # Analyse de la matrice : si une action d'écriture/suppression a plus d'un acteur,
        # on autorise si une règle 'sharedBy' couvre exactement cet ensemble d'acteurs,
        # ou si une règle 'ownedBy' protège déjà cette action au niveau de chaque
        # enregistrement (auquel cas plusieurs acteurs peuvent légitimement partager
        # le droit, puisque chacun ne peut de toute façon agir que sur ses propres
        # données) — sinon on lève une exception stricte pour forcer le refactoring.
        for entity, actions in access_matrix.items():
            for act_type, authorized_actors in actions.items():
                if len(authorized_actors) > 1 and act_type in ["Create", "Update", "Delete"]:
                    key = f"{entity}.{act_type}"
                    allowed_shared = shared_permissions.get(key)

                    if allowed_shared and authorized_actors.issubset(allowed_shared):
                        print(f"🤝 [SHARED_PRIVILEGE] L'action '{act_type}' sur '{entity}' est explicitement "
                              f"partagée entre [{', '.join(sorted(authorized_actors))}] via une règle 'sharedBy'.")
                        continue

                    # AJOUT (roadmap) : combinaison ownedBy + sharedBy implicite.
                    if (entity, act_type) in self.ownership_rules:
                        print(f"🔐 [SHARED_PRIVILEGE_VIA_OWNERSHIP] L'action '{act_type}' sur '{entity}' est partagée "
                              f"entre [{', '.join(sorted(authorized_actors))}], mais protégée au niveau de chaque "
                              f"enregistrement par la règle 'ownedBy' (propriétaire : "
                              f"{self.ownership_rules[(entity, act_type)]}).")
                        continue

                    actors_list = ", ".join(sorted(authorized_actors))
                    suggestion = f"'rule {entity}.{act_type} sharedBy {actors_list}'"
                    extra = ""
                    if allowed_shared:
                        not_covered = authorized_actors - allowed_shared
                        extra = (f" Une règle 'sharedBy' existe déjà pour '{key}' mais ne couvre pas : "
                                 f"[{', '.join(sorted(not_covered))}].")

                    raise ASTValidationError(
                        f"🔒 [CRITICAL_COLLISION] Conflit d'autorité sur l'entité '{entity}' : "
                        f"les acteurs [{actors_list}] ont tous le droit d'exécuter l'action '{act_type}'. "
                        f"Séparez ces privilèges, ou déclarez explicitement le partage avec : {suggestion}.{extra}"
                    )

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

    def to_normalized_ast(self, security_reports):
        return {
            "meta": {"appName": self.app_name, "security_audit_logs": security_reports},
            "schema": {"entities": self.entities, "relations": self.relations},
            "security": {
                "actors": list(self.actors),
                "self_register_actors": list(self.self_register_actors),
                "rules": self.rules, "workflows": self.workflows,
                "ownership": {f"{k[0]}.{k[1]}": v for k, v in self.ownership_rules.items()},
                "transitive_ownership": self.transitive_ownership,
                "access_parties": {f"{k[0]}.{k[1]}": v for k, v in self.access_party_rules.items()},
                "public": [f"{e}.{a}" for e, a in sorted(self.public_actions)],
                "hidden_fields": [f"{e}.{f}" for e, f in sorted(self.masked_fields)],
                "reputation_rules": self.reputation_rules,
                "categorized_fields": self.categorized_fields,
                "generated_fields": self.generated_fields,
                "timestamp_fields": self.timestamp_fields,
                "numbered_fields": self.numbered_fields,
                "required_profiles": self.required_profiles,
                "payable_fields": self.payable_fields,
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
                # BRIQUE 20 (point 98) : [{entity, field, value, releases}] —
                # atteindre la valeur rend ce que les enfants ont consommé.
                "release_rules": self.release_rules,
            },
            "sandbox_ai": {"custom_functions": list(self.custom_logic.values())},
            "ui": self.ui_overrides,
            "landing": self.landing,
            "capabilities": self.capabilities,
            "seeds": self.seeds,
            "assets": self.assets,
        }
