"""Écrire la spec, et la faire REVALIDER par le vrai parseur.

L'outil écrit, le compilateur prouve : la spec produite est relue par le
vrai parseur avant d'être écrite sur le disque."""

from .fondations import SEEDABLE_TYPES, DialogueError


class EmissionMixin:
    """Écrire la spec, et la faire REVALIDER par le vrai parseur."""

    def _recap(self, app_name, entities, actors, self_register, public_read, owned,
               payable=None):
        """Dernier regard sur ce qui va être écrit, avant compilation."""
        lignes = [
            ("Application", app_name),
            ("Entités", ", ".join(entities) or "aucune"),
            ("Rôles", ", ".join(actors) or "aucun"),
            ("Inscription en ligne", self_register or "fermée (manage.py)"),
            ("Lisible sans compte", ", ".join(public_read) or "rien"),
        ]
        prives = [e for e in owned if e not in public_read]
        if prives:
            lignes.append(("Lecture réservée au propriétaire", ", ".join(prives)))
        if owned:
            lignes.append(("Propriété par créateur",
                           ", ".join(f"{e} ({a})" for e, a in owned.items())))
        if payable:
            lignes.append((
                "Montant encaissé",
                f"{payable['entity']}.{payable['field']} — calculé par le serveur "
                f"({payable['source_entity']}.{payable['source_field']} × "
                f"{payable['factor']}), clé Stripe requise"))
        self._show(self.ui.recap("Ce que la spec va déclarer", lignes))

    # ---------- émission déterministe de la spec ----------
    def _emit_spec(self, app_name, description, entities, relations, actors,
                   managers, readers, public_read, public_create,
                   owned, want_seed, want_landing, design_intent=None,
                   sections=(), links=(),
                   image_topic=None,
                   self_register=None, extra_rules=(), extra_workflows=(),
                   custom_seeds=None,
                   payable=None, account_identifier=None):
        lines = [f"app {app_name}", "",
                 "# Spécification générée par le dialogue guidé monl (déterministe, sans IA).",
                 f"# Brief du projet : {description}"]
        # Écrit AUSSI en commentaire : sans bloc `landing`, la spec n'a pas de
        # brief où porter le sujet, et l'humain qui rouvre le fichier doit
        # quand même savoir ce qu'il avait demandé. Un commentaire ne va pas au
        # contrat — c'est assumé : il documente, il ne promet rien.
        if image_topic:
            lines.append(f"# Sujet des illustrations : {image_topic}")
        lines.append("")

        for ent, fields in entities.items():
            lines.append(f"entity {ent}")
            for fname, ftype in fields:
                lines.append(f"    {fname}: {ftype}")
            lines.append("")

        for src, rtype, tgt in relations:
            lines.append(f"relation {src} {rtype} {tgt}")
        if relations:
            lines.append("")

        # CORRECTIF (bêta 3) : sans le marqueur 'selfRegister', '/register'
        # refuse toute inscription — une spec issue du dialogue produisait donc
        # une application dont personne ne pouvait créer de compte.
        for act in actors:
            lines.append(f"actor {act} selfRegister" if act == self_register
                         else f"actor {act}")
        lines.append("")

        # POINT 95, posé par le dialogue depuis le point 138. Rien n'est émis
        # quand l'humain n'a rien choisi : un bloc `capability auth` vide n'est
        # PAS la même chose qu'aucun bloc, et deviner « email par défaut »
        # verrouillerait tous les projets existants.
        if account_identifier:
            lines.append("# La FORME de l'identifiant de compte est vérifiée ET normalisée :")
            lines.append("# sans forme canonique, une majuscule de plus fait un second compte.")
            lines.append("capability auth")
            lines.append(f"    identifier: {', '.join(account_identifier['formes'])}")
            if account_identifier.get("prefixe"):
                lines.append(f'    phone_prefix: "{account_identifier["prefixe"]}"')
            lines.append("")

        # POINT 86 : les champs que le SERVEUR calcule ne peuvent pas être
        # « requis » — le client ne peut pas les envoyer. Le dialogue posait la
        # règle sur le premier champ de chaque entité sans regarder si la brique
        # de paiement venait de lui retirer le droit d'être écrit.
        calcules_par_le_serveur = set()
        if payable:
            porte = payable.get("line_entity") or payable["entity"]
            calcules_par_le_serveur.add((payable["entity"], payable["field"]))
            calcules_par_le_serveur.add(
                (porte, self.CHAMP_SOUS_TOTAL if payable.get("line_entity")
                 else payable["field"]))

        # Règles : premier champ requis, lecture/création publiques
        for ent, fields in entities.items():
            first_field = fields[0][0]
            if (ent, first_field) in calcules_par_le_serveur:
                continue
            lines.append(f"rule {ent}.{first_field} required")
        # Une visibilité conditionnelle remplace la visibilité publique
        # inconditionnelle : conserver les deux règles ferait échouer le
        # validateur et, surtout, rendrait le filtre métier inopérant.
        public_when_entities = {
            rule.split()[1].split(".", 1)[0]
            for rule in extra_rules
            if rule.startswith("rule ") and " publicWhen " in rule
        }
        for ent in public_read:
            if ent not in public_when_entities:
                lines.append(f"rule {ent}.Read public")
        for ent in public_create:
            lines.append(f"rule {ent}.Create public")
        for ent, owner in owned.items():
            # CORRECTIF (bêta 3, fuite entre comptes) : une entité possédée par
            # ses créateurs ET non lisible sans compte est de la donnée privée
            # (dépenses, commandes, tâches personnelles). Sans cette règle, tout
            # titulaire d'un compte listait les enregistrements de tous les
            # autres — seule l'écriture était protégée. La règle est écrite en
            # clair dans la spec : elle reste relisable et supprimable.
            if ent not in public_read:
                lines.append(f"rule {ent}.Read ownedBy {owner}")
            lines.append(f"rule {ent}.Update ownedBy {owner}")
            lines.append(f"rule {ent}.Delete ownedBy {owner}")
        for ent in entities:
            if len(managers[ent]) > 1:
                shared_list = ", ".join(managers[ent])
                for action in ("Create", "Update", "Delete"):
                    lines.append(f"rule {ent}.{action} sharedBy {shared_list}")
        if payable:
            # POINT 75 : les règles sont écrites en clair, avec ce qu'elles
            # déclenchent. L'auteur doit pouvoir les relire — et les supprimer —
            # sans ouvrir la documentation : c'est le seul endroit de la spec
            # qui fasse sortir une requête du backend.
            entite, montant = payable["entity"], payable["field"]
            source, prix = payable["source_entity"], payable["source_field"]
            lines.append("")
            lines.append("# POINT 89 : la date d'arrivée, écrite par le serveur à la")
            lines.append("# création et jamais ensuite. Elle disparaît des corps de")
            lines.append("# requête : une date qu'on se donne à soi-même n'atteste de")
            lines.append(f"# rien, et un carnet de {entite} où chacun choisit ses dates")
            lines.append("# ne dit plus dans quel ordre honorer.")
            lines.append(f"rule {entite}.{self.CHAMP_DATE} timestamp")
            facteur = payable["factor"]
            ligne = payable.get("line_entity")
            # POINT 86 : deux formes possibles. Sans panier, le montant est
            # calculé sur l'entité encaissée elle-même (forme du point 77) ;
            # avec panier, il est la SOMME des sous-totaux de ses lignes
            # (point 82). Les deux satisfont l'exigence du point 79 — un montant
            # qu'aucun corps de requête ne peut porter.
            porteur = ligne or entite
            calcule = payable.get("line_subtotal", self.CHAMP_SOUS_TOTAL) if ligne else montant
            lines.append("")
            if not ligne:
                lines.append("# La quantité est le seul chiffre que l'acheteur fournit,")
                lines.append("# et elle est obligatoire : sans elle le calcul ci-dessous")
                lines.append("# porterait sur du vide.")
                lines.append(f"rule {entite}.{facteur} required")
                lines.append("")
            lines.append("# POINT 79 : le montant est CALCULÉ PAR LE SERVEUR — prix au")
            lines.append(f"# catalogue ({source}.{prix}) multiplié par la quantité. Le")
            lines.append(f"# champ {porteur}.{calcule} disparaît donc des corps de requête,")
            lines.append("# à la création comme à la modification. Sans ce calcul,")
            lines.append("# l'acheteur fixerait lui-même ce qu'il règle : il devient")
            lines.append("# propriétaire de ce qu'il crée, donc le payeur.")
            lines.append(f"rule {porteur}.{calcule} derivedFrom {source}.{prix} by {facteur}")
            lines.append("")
            if ligne:
                lines.append("# POINT 82 : le total du panier est la SOMME de ses lignes,")
                lines.append("# recalculée par le serveur à chaque ligne ajoutée, modifiée")
                lines.append("# ou supprimée. Sommer un sous-total que le navigateur")
                lines.append("# écrirait serait la faille du point 77 en une addition de")
                lines.append("# plus : le compilateur le refuse.")
                lines.append(f"rule {entite}.{montant} sumOf {ligne}.{calcule}")
                lines.append("")
            if payable.get("stock_field"):
                stock = payable["stock_field"]
                lines.append("# POINT 85 : ce plancher n'est pas décoratif — c'est lui qui")
                lines.append("# arme la vérification de disponibilité ci-dessous. Sans lui,")
                lines.append("# le décompte passerait sous zéro et le stock mentirait.")
                lines.append(f"rule {source}.{stock} min 0")
                lines.append("")
                lines.append("# POINT 86 : le stock suit les commandes, et retire CE QUE LE")
                lines.append("# CLIENT A DEMANDÉ — pas une constante. Commander plus que le")
                lines.append("# stock disponible répond 409, sans rien décompter.")
                lines.append(f"rule {porteur}.Create decrements {source}.{stock} by {facteur}")
                lines.append("")
            lines.append("# Encaissement : le champ nommé porte le MONTANT, donc")
            lines.append("# l'entité à encaisser. Deux routes en découlent —")
            lines.append("# POST /entite/{id}/paiement (aucun corps : le montant est")
            lines.append("# relu en base) et POST /paiement/webhook, dont la")
            lines.append("# signature est vérifiée. Sans STRIPE_SECRET_KEY, elles")
            lines.append("# répondent 503 ; le reste de l'application fonctionne.")
            lines.append(f"rule {entite}.{montant} payable")
            lines.append("")
        # Règles avancées portées par les modèles du catalogue (increments,
        # hidden, categorized…) — émises telles quelles, validées comme tout
        # le reste par le parseur + l'audit en sortie de dialogue.
        # Les règles post-paiement ne sont valides que si le dialogue a
        # effectivement activé le paiement. Le modèle reste donc compilable
        # quand l'utilisateur refuse cette option.
        rules_to_emit = [
            rule for rule in extra_rules
            if payable or " writableAfterPayment " not in f" {rule} "
        ]
        lines.extend(rules_to_emit)
        lines.append("")

        # Workflows : un gestionnaire CRUD complet par entité (jamais de
        # collision d'écriture), puis un workflow de lecture par lecteur.
        for ent in entities:
            for actor in managers[ent]:
                suffix = f"By{actor}" if len(managers[ent]) > 1 else ""
                lines.append(f"workflow Manage{ent}{suffix} for {actor}")
                for action in ("Create", "Read", "Update", "Delete"):
                    lines.append(f"    {action} {ent}")
                lines.append("")
        for workflow in extra_workflows:
            lines.append(f"workflow {workflow['name']} for {workflow['actor']}")
            for action, target in workflow["actions"]:
                lines.append(f"    {action} {target}")
            lines.append("")
        for act in actors:
            readable = [ent for ent in entities if act in readers[ent]]
            if readable:
                lines.append(f"workflow Browse{act} for {act}")
                for ent in readable:
                    lines.append(f"    Read {ent}")
                lines.append("")

        if want_seed:
            custom_seeds = custom_seeds or {}
            # Données réalistes du modèle en priorité ; repli générique pour
            # les entités publiques qui n'en ont pas.
            for ent, rows in custom_seeds.items():
                if not rows or ent not in entities:
                    continue
                lines.append(f"seed {ent}")
                for row in rows:
                    parts = []
                    for f, v in row.items():
                        parts.append(f"{f}: {self._literal(v)}")
                    lines.append("    " + ", ".join(parts))
                lines.append("")
            for ent in public_read:
                if ent in custom_seeds:
                    continue
                seedable = [(f, t) for f, t in entities[ent] if t in SEEDABLE_TYPES]
                if not seedable:
                    continue
                lines.append(f"seed {ent}")
                for n in (1, 2, 3):
                    parts = [f"{f}: {self._seed_value(f, t, n, image_topic)}"
                             for f, t in seedable]
                    lines.append("    " + ", ".join(parts))
                lines.append("")

        if want_landing:
            # Le brief porte la description ET l'intention visuelle : c'est la
            # seule phrase du contrat qui dise à l'IA UI à quoi sert le site
            # (point 53). Le commentaire d'en-tête, lui, reste court.
            brief = (f"{description.rstrip('.')} — {design_intent}"
                     if design_intent else description)
            # Le sujet d'illustration ne produit plus d'URL distante : il part
            # ICI, dans la seule phrase du contrat que l'IA d'interface lit
            # pour savoir à quoi sert le site. Sans ce report, la question du
            # dialogue deviendrait une question sans effet — ce que le
            # point 85 interdit au compilateur, et qui vaut autant pour le
            # dialogue qui écrit la spec.
            if image_topic:
                brief = (f"{brief.rstrip('.')}. Les illustrations doivent "
                         f"évoquer : {image_topic}.")
            lines.append("landing")
            lines.append(f'    brief: "{brief}"')
            for s in sections:
                lines.append(f'    section "{s["title"]}": "{s["body"]}"')
            # Brique 30 : les destinations du pied de page. Sans elles, le
            # pied sort sans un seul lien — et rien dans la spec ne peut les
            # inventer, pas plus qu'une entité ne peut porter un « à propos ».
            for lien in links:
                lines.append(f'    link "{lien["label"]}": "{lien["url"]}"')
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _literal(value):
        """Valeur de seed -> littéral DSL (la grammaire n'accepte que
        STRING_LITERAL et SIGNED_NUMBER)."""
        if isinstance(value, bool):
            raise DialogueError("un seed ne peut pas contenir de booléen (grammaire)")
        if isinstance(value, (int, float)):
            return str(value)
        return '"' + str(value).replace('"', "'") + '"'

    @staticmethod
    def _seed_value(field_name, ftype, n, image_topic=None):
        low = field_name.lower()
        if ftype in ("Integer",):
            return str(n * 10)
        if ftype in ("Float", "Money"):
            return f"{n * 10}.5"
        if ftype == "Email":
            return f'"demo{n}@exemple.fr"'
        if any(k in low for k in ("image", "photo", "url", "cover", "avatar")):
            # VIDE, jamais une URL distante : une démonstration qui va chercher
            # ses images chez un tiers contredit l'autonomie que monl promet, et
            # ne s'ouvre pas hors ligne. La vraie photo passe par
            # `monl assets add` (brique 13). Voir `_img` dans app_templates.py.
            return '""'
        if ftype == "Text":
            return f'"Contenu de démonstration numéro {n}, généré par le dialogue guidé."'
        return f'"Exemple {n}"'
