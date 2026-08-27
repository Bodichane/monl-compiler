"""L'empreinte du contrat — HUIT ensembles, et un dictionnaire.

L'ANGLE MORT DU DELTA, huit fois (points 88 à 116) : une brique qui ajoute
une promesse au contrat doit se demander si cette fonction la VOIT. Six
fois la réponse a été non, et six fois `monl update` aurait répondu
« aucun changement d'interface » en laissant un écran entier à écrire."""

import hashlib
import json


def _contract_signature(contract):
    routes = {f"{r['method']} {r['path']}" for r in contract["routes"]}
    fields = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
              for f in spec["fields"]}
    field_types = {f"{e}.{f['name']}": f["type"]
                   for e, spec in contract["entities"].items()
                   for f in spec["fields"]}
    # POINT 88 : QUI a le droit d'appeler une route fait partie de l'interface.
    # Le delta ne comparait que méthode+chemin : ouvrir le carnet de commandes
    # à l'administrateur ne créait aucune route nouvelle — seulement un acteur
    # de plus sur des routes existantes — et 'monl update' répondait « aucun
    # changement d'interface, le frontend existant reste valide ». C'était vrai
    # et trompeur : rien n'était cassé, mais tout un écran manquait, et le
    # rapport de delta existe précisément pour dire ce qu'il reste à écrire.
    acces = {f"{r['method']} {r['path']} → {acteur}"
             for r in contract["routes"]
             for acteur in r.get("allowed_actors") or []}
    # POINT 89 : un champ n'est pas seulement présent ou absent — il est
    # SAISISSABLE ou non, et ça change autant l'interface. Poser
    # 'rule Order.total derivedFrom …' sur un champ qui existait déjà ne
    # renomme rien : le delta répondait « aucun changement » pendant que le
    # formulaire de prix devenait un champ que le serveur ignore. Le même angle
    # mort que le point 88, sur l'autre moitié du contrat.
    lecture_seule = {f"{e}.{f['name']}" for e, spec in contract["entities"].items()
                     for f in spec["fields"] if f.get("server_generated")}
    # POINT 90 : troisième forme du même angle mort. Une route peut gagner un
    # PRÉALABLE sans changer de chemin, d'acteurs ni de champs — et le frontend
    # doit pourtant être réécrit : ici, créer la fiche avant le tunnel d'achat,
    # sous peine de 409 au dernier écran. Comparer les routes ne suffisait pas,
    # comparer les acteurs (point 88) ni les champs en lecture seule (point 89)
    # non plus. C'est la troisième fois : le delta doit comparer TOUT ce que le
    # contrat promet, pas seulement ce qui a un nom nouveau.
    prealables = {f"{r['method']} {r['path']} → exige un {r['requires_own']}"
                  for r in contract["routes"] if r.get("requires_own")}
    # POINT 91 : quatrième fois. Poser 'payable' fige les écritures sur
    # l'enregistrement encaissé ET sur ses lignes : les routes ne changent ni de
    # chemin, ni d'acteurs, ni de champs, mais un bouton « Modifier » dessiné
    # sans le savoir mène à un 409. Un verrou porté par une route qui vient
    # d'apparaître est exclu du rapport — déjà dit par « route ajoutée », même
    # arbitrage anti-doublon qu'aux points 88 à 90.
    verrous = {f"{r['method']} {r['path']} → figé une fois {r['payment_locked']} réglé"
               for r in contract["routes"] if r.get("payment_locked")}
    # POINT 94 : cinquième fois, et la première qui ne concerne pas les données.
    # Le delta ne regardait QUE l'API — ajouter une rubrique éditoriale ou une
    # question de FAQ ne touche aucune route, aucun champ, et 'monl update'
    # répondait « aucun changement d'interface » alors qu'il restait un bloc
    # entier à écrire sur l'accueil. L'angle mort existait pour `section`
    # depuis le point 55 ; la FAQ y serait tombée le jour de sa naissance.
    #
    # Un DICTIONNAIRE et non un ensemble, contrairement aux six autres : le
    # texte compte autant que le titre. Comparer les seuls titres, c'est
    # l'erreur exacte du point 89 — réécrire « Livraison et retours » de fond en
    # comble ne renomme rien, et il faut pourtant re-rendre la page.
    contenus = {f"section « {s['title']} »": hashlib.sha256(
                    "\n".join(s["body"]).encode("utf-8")).hexdigest()
                for s in contract.get("sections") or []}
    # BRIQUE 30 : DIXIÈME fois, et la question posée avant d'écrire la brique.
    # Déclarer un lien de pied de page ne crée aucune route, ne renomme aucun
    # champ, ne touche à aucun acteur — et le pied de page doit être réécrit,
    # sous peine d'un refus « lien déclaré absent du site ». L'ADRESSE entre
    # dans le digest, pas seulement le libellé : corriger une faute de frappe
    # dans une URL ne renomme rien non plus (leçon des points 89 et 96).
    contenus.update({f"lien « {lien['label']} »": hashlib.sha256(
                         lien["url"].encode("utf-8")).hexdigest()
                     for lien in contract.get("links") or []})
    contenus.update({f"question « {q['question']} »": hashlib.sha256(
                         "\n".join(q["answer"]).encode("utf-8")).hexdigest()
                     for q in contract.get("faq") or []})
    # POINT 95 : la question du point 94, posée AVANT d'écrire la brique cette
    # fois. Déclarer 'identifier: email' ne crée aucune route et ne renomme
    # aucun champ — le corps de '/register' garde les mêmes clés — mais l'écran
    # d'inscription change : étiquette, type de saisie, message d'erreur. Sans
    # ça, le delta aurait dit « aucun changement d'interface » pendant qu'un
    # formulaire se mettait à répondre 422 sans expliquer pourquoi.
    formes = (contract.get("api", {}).get("auth", {}).get("register", {})
              .get("identifier_forms") or [])
    if formes:
        contenus[f"identifiant de compte ({', '.join(formes)})"] = "forme"
    # POINT 96 : sixième fois. Poser `oneOf` sur un champ existant ne renomme
    # rien — mais un champ texte devient un MENU, et la liste des valeurs peut
    # changer sans que le champ bouge (« expédiée » ajoutée au carnet). Le
    # digest porte donc les valeurs, pas seulement leur présence : comparer les
    # seuls noms serait l'erreur du point 89, pour la troisième fois.
    # POINT 98 : septième fois. Poser `releases` ne crée aucune route et ne
    # change aucun champ — mais un bouton « réactiver » devient un 409, et un
    # écran doit expliquer que l'annulation rend le stock. Le delta le dit.
    for r in contract["routes"]:
        lib = r.get("releases_on")
        if lib:
            contenus[f"libération de {r['method']} {r['path']}"] = hashlib.sha256(
                f"{lib['field']}\n{lib['value']}\n{lib['releases']}".encode()
            ).hexdigest()
    for entite, spec in sorted((contract.get("entities") or {}).items()):
        for champ in spec.get("fields") or []:
            if champ.get("allowed_values"):
                contenus[f"choix de {entite}.{champ['name']}"] = hashlib.sha256(
                    "\n".join(champ["allowed_values"]).encode("utf-8")).hexdigest()
            # BRIQUE B1 : un Upload contraint une entrée frontend même si le
            # champ existait déjà. La signature porte les octets de contrat
            # (nom multipart, limite et MIME), pas une valeur téléversée.
            # Une modification de max/types déclenche donc bien le delta ; une
            # spec sans Upload n'ajoute aucune entrée et conserve sa signature.
            if champ.get("upload"):
                contenus[f"upload de {entite}.{champ['name']}"] = hashlib.sha256(
                    json.dumps(champ["upload"], sort_keys=True,
                               ensure_ascii=False).encode("utf-8")).hexdigest()
    # POINT 116 : neuvième et dixième fois. `publicWhen` et `oncePer` vivent
    # dans `business_rules`, que la signature ne lisait pas : poser
    # 'rule Article.Read publicWhen status "published"' ne crée aucune route,
    # ne renomme aucun champ et ne change aucun acteur — `monl update`
    # répondait « aucun changement d'interface » pendant qu'il fallait
    # dessiner un état « brouillon », un filtre de liste et un écran de
    # modération. `oncePer` est le même angle mort côté écriture : le bouton
    # « voter » gagne un 409 que personne n'a annoncé. La VALEUR entre dans le
    # digest, pas seulement la présence de la règle : passer de "published" à
    # "validated" ne renomme rien non plus (leçon des points 89 et 96).
    regles_metier = contract.get("business_rules") or {}
    for reference, condition in sorted((regles_metier.get("public_when") or {}).items()):
        contenus[f"publication conditionnelle de {reference}"] = hashlib.sha256(
            f"{condition.get('field')}\n{condition.get('value')}".encode()).hexdigest()
    for regle in regles_metier.get("once_per") or []:
        contenus[f"unicité de {regle['trigger_entity']}"] = hashlib.sha256(
            "\n".join(regle["parents"]).encode("utf-8")).hexdigest()
    # BRIQUE 2a : douzième fois, et la question posée AVANT d'écrire la brique.
    # Passer de EUR à XOF ne crée aucune route, ne renomme aucun champ et ne
    # change aucun acteur — mais TOUS les prix affichés changent de symbole, et
    # la division par cent qu'une interface fait pour l'euro devient fausse. Un
    # frontend écrit avant le changement affiche donc des euros sur des francs
    # CFA, ou un centième du montant. L'EXPOSANT entre dans le digest autant
    # que le code : deux devises peuvent partager un symbole et pas leurs
    # décimales, et ne comparer que le code serait l'erreur du point 89.
    paiement = regles_metier.get("payment")
    if paiement:
        # Le PRESTATAIRE entre dans le même digest (brique 2b) : passer de
        # Stripe à FedaPay ne change ni route ni champ, mais l'écran de
        # règlement cesse de parler de carte bancaire pour parler d'opérateurs
        # de mobile money.
        contenus["devise d'encaissement"] = hashlib.sha256(
            f"{paiement.get('provider')}\n{paiement.get('currency')}\n"
            f"{paiement.get('minor_unit_exponent')}".encode()).hexdigest()
    # BRIQUE B2 : un message n'ajoute pas de route, mais il change le parcours
    # après une création et le texte que l'interface doit afficher. Le delta
    # porte sur le déclencheur, le destinataire annoncé et le contenu complet ;
    # comparer seulement la présence de la règle laisserait passer une
    # modification de sujet ou de corps.
    for message in regles_metier.get("messages") or []:
        reference = message["trigger"]
        contenus[f"message sortant de {reference}"] = hashlib.sha256(
            json.dumps(message, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    # BRIQUE B3 : un filtre ou un tri ajoute un travail frontend même si les
    # routes et les champs portent les mêmes noms. Le digest porte la whitelist,
    # les valeurs finies et les deux sens de tri ; une modification de cette
    # capacité doit donc déclencher le delta de contrat.
    for route in contract.get("routes") or []:
        query = route.get("list_query")
        if query:
            contenus[f"capacités de liste de {route['method']} {route['path']}"] = hashlib.sha256(
                json.dumps(query, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest()
    # BRIQUE B4 : le verrouillage et les paramètres de session/TOTP changent
    # des écrans sans forcément ajouter un champ métier. La signature porte
    # la configuration complète, y compris les durées et les garanties de
    # rotation/rejeu. Une spec sans B4 n'ajoute aucune entrée.
    auth_features = (contract.get("api", {}).get("auth", {}).get("features") or {})
    if auth_features:
        contenus["authentification B4"] = hashlib.sha256(
            json.dumps(auth_features, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    # POINT 99 : huitième ensemble, et la question posée AVANT d'écrire le code
    # pour la deuxième fois seulement. Une clé étrangère ne vit pas dans
    # `fields` — le delta ne pouvait donc rien dire quand elle change de NATURE.
    # Or elle en change de deux façons, et les deux réécrivent un écran :
    #
    #   - ce qu'elle CONTIENT : un id de compte ou l'id d'une ligne métier. Le
    #     contrat le dit depuis le point 88, précisément parce qu'une jointure
    #     faite sur la mauvaise des deux marche À MOITIÉ ;
    #   - qui la RENSEIGNE : le serveur depuis le jeton, ou le client. Passer du
    #     premier au second ajoute un champ obligatoire au formulaire de
    #     création — un menu de produits sur « nouvelle variante » — sans
    #     renommer quoi que ce soit. Sans cette ligne, `monl update` répondait
    #     « aucun changement d'interface » et le POST récoltait un 422.
    liens = set()
    for entite, spec in sorted((contract.get("entities") or {}).items()):
        designees = set(spec.get("client_foreign_keys") or [])
        for lien in spec.get("foreign_keys") or []:
            porte = ("un identifiant de compte" if lien.get("references_account")
                     else f"l'id d'un {lien['references']}")
            par = "à envoyer par le client" if lien["column"] in designees \
                else "renseigné par le serveur"
            liens.add(f"{entite}.{lien['column']} → {porte}, {par}")
    # POINT 119 : NEUVIÈME fois, et la question posée avant d'écrire la brique
    # cette fois-ci. Le plancher de sections et la substance exigée de chacune
    # ne créent aucune route, ne renomment aucun champ et ne touchent à aucun
    # acteur — mais un site conforme hier devient non conforme, et
    # `monl run --check` le refuse. Sans cette entrée, `monl update` répondrait
    # « aucun changement d'interface » juste avant que le site cesse de
    # démarrer : le pire des deux mondes. Le digest porte la RÈGLE et pas
    # seulement le nom de la section — relever le seuil de texte de `trust`
    # oblige aussi à réécrire, exactement comme au point 89.
    from ..design_system import _section_substance, infer_design_profile
    profil = infer_design_profile(contract)
    sections_obligatoires = {
        marker.partition("=")[2].strip('"'): hashlib.sha256(
            json.dumps(regle, sort_keys=True).encode("utf-8")).hexdigest()
        for marker, regle in _section_substance(contract, profil).items()
    }
    return (routes, fields, acces, lecture_seule, prealables, verrous,
            contenus, liens, field_types, sections_obligatoires)
