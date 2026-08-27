"""Les deux routes d'encaissement.

Trois invariants à ne jamais assouplir : le montant est lu EN BASE et la
route n'accepte AUCUN corps ; la signature du webhook est vérifiée avant
toute écriture — c'est le SEUL endroit du backend généré où un tiers non
authentifié écrit ; une clé absente donne 503 en la NOMMANT, sans empêcher
le reste du serveur de fonctionner."""

class PaiementRoutesMixin:
    """Les deux routes d'encaissement."""

    # ─────────────────────────────────────────────────────────────────
    # BRIQUE PAIEMENT (point 74). Deux routes seulement, et un principe :
    # le montant encaissé vient de la BASE, jamais du client. Un panier
    # qui envoie son propre prix est un panier qu'on peut négocier.
    #
    # Les secrets viennent de l'environnement (même règle que le secret
    # JWT). Absents, les routes existent mais répondent 503 en nommant la
    # variable manquante : un paiement doit refuser bruyamment, jamais
    # échouer en silence — et le smoke test reste vert hors ligne.
    # ─────────────────────────────────────────────────────────────────

    def _generate_payment_routes(self):
        if not self.payable_by_entity:
            return []
        # BRIQUE 2a : la devise vient du validateur DÉJÀ résolue en
        # {code, exponent} ; ici on ne fait que la lire. Le défaut n'est
        # appliqué qu'à cet endroit — pas dans le validateur — pour qu'une spec
        # muette continue de produire exactement ce qu'elle produisait
        # (`payment_currency is None` ⇒ EUR, exposant 2 ⇒ ×100 comme avant).
        devise = self.payment_currency or {"code": "EUR", "exponent": 2}
        code_devise = devise["code"].lower()
        exposant_devise = devise["exponent"]
        # BRIQUE 2b : le prestataire. `None` ⇒ Stripe, et l'émission Stripe est
        # laissée INTACTE à l'octet — condition pour qu'aucun projet existant ne
        # voie son app.py bouger. FedaPay est une SECONDE émission, pas une
        # généralisation de la première : ce qui se factorise est le noyau de
        # sécurité (montant lu en base, signature vérifiée avant toute écriture,
        # 503 nommant la variable, référence qualifiée), pas la forme du fil.
        prestataire = self.payment_provider or "stripe"
        # Ce qui DIFFÈRE d'un prestataire à l'autre au webhook : le nom du
        # secret, l'en-tête, et la lettre du schéma de signature. Le reste — le
        # HMAC-SHA256 de « horodatage.corps brut », la tolérance de cinq
        # minutes, la vérification AVANT toute écriture — est identique, et
        # c'est précisément ce qui se factorise. La recette FedaPay a été
        # relue dans son SDK officiel (Webhook.ts : EXPECTED_SCHEME = 's',
        # `${timestamp}.${payload}`, sha256 hex, DEFAULT_TOLERANCE = 300),
        # jamais déduite d'une prose.
        if prestataire == "fedapay":
            secret_var = "FEDAPAY_WEBHOOK_SECRET"
            secret_env = "MONL_FEDAPAY_WEBHOOK_SECRET"
            entete_signature, schema_signature = "x-fedapay-signature", "s"
            cle_var, cle_env = "FEDAPAY_SECRET_KEY", "MONL_FEDAPAY_SECRET_KEY"
        else:
            secret_var = secret_env = "STRIPE_WEBHOOK_SECRET"
            entete_signature, schema_signature = "stripe-signature", "v1"
            cle_var = cle_env = "STRIPE_SECRET_KEY"
        if prestataire == "fedapay":
            lignes = self._prelude_fedapay(code_devise.upper())
        else:
            lignes = [
                "",
                "# ── Paiement (brique 'payable') ──────────────────────────────",
                "STRIPE_SECRET_KEY = (os.environ.get('STRIPE_SECRET_KEY') or '').strip()",
                "STRIPE_WEBHOOK_SECRET = (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip()",
                "# Point de terminaison surchargeable : indispensable pour éprouver",
                "# le parcours complet sans appeler Stripe (voir tests).",
                "STRIPE_BASE_URL = (os.environ.get('MONL_STRIPE_BASE_URL')",
                "                   or 'https://api.stripe.com').rstrip('/')",
                "",
                "def _exiger_cle_paiement(nom, valeur):",
                "    if not valeur:",
                "        raise HTTPException(status_code=503, detail=(",
                "            f\"Paiement indisponible : la variable d'environnement {nom} n'est pas \"",
                "            'définie sur le serveur. Aucun règlement ne peut être accepté tant '",
                "            \"qu'elle manque.\"))",
                "",
                "def _session_paiement(montant_centimes, devise, reference, retour):",
                "    \"\"\"Crée une session de règlement. Le montant est en CENTIMES,",
                "    calculé côté serveur depuis la base.\"\"\"",
                "    corps = urllib.parse.urlencode({",
                "        'mode': 'payment',",
                "        'success_url': retour + '?paiement=ok',",
                "        'cancel_url': retour + '?paiement=annule',",
                "        'client_reference_id': str(reference),",
                "        'line_items[0][quantity]': '1',",
                "        'line_items[0][price_data][currency]': devise,",
                "        'line_items[0][price_data][unit_amount]': str(montant_centimes),",
                "        'line_items[0][price_data][product_data][name]': f'Commande {reference}',",
                "    }).encode()",
                "    requete = urllib.request.Request(",
                "        STRIPE_BASE_URL + '/v1/checkout/sessions', data=corps, method='POST')",
                "    requete.add_header('Authorization', 'Bearer ' + STRIPE_SECRET_KEY)",
                "    requete.add_header('Content-Type', 'application/x-www-form-urlencoded')",
                "    try:",
                "        with urllib.request.urlopen(requete, timeout=15) as reponse:",
                "            return json.loads(reponse.read() or b'{}')",
                "    except urllib.error.HTTPError as e:",
                "        with e:",
                "            detail = (e.read() or b'')[:400].decode('utf-8', 'replace')",
                "        raise HTTPException(status_code=502, detail=(",
                "            f'Le prestataire de paiement a refusé la demande ({e.code}) : {detail}'))",
                "    except urllib.error.URLError as e:",
                "        raise HTTPException(status_code=502, detail=(",
                "            f'Prestataire de paiement injoignable : {e.reason}'))",
                "",
            ]
        for entite, champ in sorted(self.payable_by_entity.items()):
            table = entite.lower()
            # POINT 99 : la colonne comparée à `current_user_id` doit porter un
            # identifiant de COMPTE — donc celle de `_identity_fk_columns`, et
            # non la première relation entrante venue. Sur une entité fille
            # d'une table métier, cette première relation porte l'id d'une ligne
            # de catalogue : la comparaison aurait été fausse dans les deux sens
            # (le propriétaire ne peut plus payer, un inconnu le peut si les
            # deux identifiants coïncident). Le validateur refuse désormais ce
            # cas ; l'assertion plus bas garantit qu'aucune divergence entre lui
            # et cette ligne ne puisse écrire une route sans contrôle.
            colonnes_compte = self._identity_fk_columns().get(entite, set())
            proprio = ({"fk_column": sorted(colonnes_compte)[0]}
                       if colonnes_compte else None)
            # POINT 87 : sous propriété TRANSITIVE, la clé étrangère de l'entité
            # désigne l'intermédiaire, pas un compte — c'est pourquoi le
            # point 81 refusait d'encaisser ici. Une jointure d'un cran rend
            # l'id de COMPTE, donc la comparaison qui suit est identique au cas
            # direct : rien d'autre ne change dans cette route.
            #
            # L'invariant à ne PAS casser : le montant, l'état et le
            # propriétaire sortent de la MÊME lecture. Deux requêtes séparées
            # rouvriraient la fenêtre entre le contrôle d'accès et le calcul du
            # montant — donc la jointure entre DANS le SELECT, elle ne s'ajoute
            # pas à côté.
            chaine = self._transitive_chain(entite)
            if not chaine and not proprio:
                # POINT 99 : sans propriétaire, la route encaisserait n'importe
                # quel enregistrement pour n'importe quel appelant authentifié
                # (IDOR). Le validateur l'interdit — arriver ici signifie qu'il a
                # divergé de cette couche. Échouer à la génération vaut mieux
                # qu'écrire une route de paiement sans contrôle d'accès, même
                # raisonnement que `_derived_source_fk`.
                raise ValueError(
                    f"Génération : '{entite}' est 'payable' mais aucune colonne ne "
                    f"porte l'identifiant du compte propriétaire — la route de "
                    f"règlement ne pourrait opposer de 403 à personne.")
            if chaine:
                # Briques 11 et 24 : une chaîne de JOIN, une par maillon, jusqu'au
                # compte. Montant, état et propriétaire sortent de la MÊME lecture.
                _depuis, _cur, _fk = self._chain_join(entite)
                colonnes = f't."{champ}", t.payment_status, {_cur}."{_fk}"'
                depuis = _depuis
            else:
                colonnes = (f'"{champ}", payment_status, "{proprio["fk_column"]}"')
                depuis = f'"{table}"'
            lignes += [
                f"@app.post('/{table}/{{id}}/paiement', tags=['Paiement'])",
                f"def payer_{table}(id: int, request: Request, "
                "current_user_id: int = Depends(get_current_user_id)):",
                f"    _exiger_cle_paiement('{cle_env}', {cle_var})",
                "    conn = _connect(); cursor = conn.cursor()",
                f"    cursor.execute('SELECT {colonnes} FROM {depuis} WHERE "
                f"{'t.' if chaine else ''}id = ?', (id,))",
                "    ligne = cursor.fetchone()",
                "    conn.close()",
                # Sous jointure, une ligne ORPHELINE (intermédiaire disparu) ne
                # rend aucun résultat : elle n'appartient à personne, et 404 est
                # la bonne réponse — surtout pas « payable par quiconque ».
                "    if not ligne:",
                "        raise HTTPException(status_code=404, detail='Introuvable.')",
            ]
            lignes += [
                "    montant, etat, proprietaire = ligne",
                "    if proprietaire is not None and proprietaire != current_user_id:",
                "        raise HTTPException(status_code=403, detail="
                "'Cet enregistrement ne vous appartient pas.')",
            ]
            lignes += [
                "    if etat == 'payee':",
                "        raise HTTPException(status_code=409, detail='Déjà réglé.')",
                # BRIQUE 2a : le prestataire attend un ENTIER dans l'unité
                # mineure de la devise, donc `montant × 10**exposant`. Le `×100`
                # figé d'avant était juste pour l'euro et faux partout ailleurs :
                # le franc CFA n'a pas de sous-unité, une commande de 5 000 FCFA
                # serait partie pour 500 000. La variable garde le nom
                # `centimes` — c'est le mot du code, pas du fil (voir plus bas).
                "    centimes = int(round(float(montant or 0) * "
                f"{10 ** exposant_devise}))",
                "    if centimes <= 0:",
                "        raise HTTPException(status_code=400, detail=(",
                "            'Montant nul ou négatif : rien à encaisser.'))",
                "    retour = str(request.base_url).rstrip('/') + '/site/'",
                # CORRECTIF SÉCURITÉ : la référence porte désormais le nom de
                # l'entité. Un simple id numérique se confondait avec celui
                # d'une AUTRE entité payable de la même app -- le webhook
                # marquait alors comme payé un enregistrement d'une table
                # totalement différente, portant seulement le même id.
                f"    reference = '{entite}:' + str(id)",
                f"    session = _session_paiement(centimes, '{code_devise}', "
                "reference, retour)",
            ]
            if prestataire == "fedapay":
                lignes += [
                    # PROUVÉ, PAS DEVINÉ : le plugin Odoo officiel de FedaPay
                    # (fedapay/fedapay-odoo, payment_transaction.py) retrouve
                    # sa commande par `notification_data.get('id')`, l'id de
                    # transaction qu'il a mémorisé à la création. On mémorise
                    # donc le même, ce qui donne au webhook une seconde façon
                    # de reconnaître l'enregistrement — indépendante de
                    # `merchant_reference`, dont l'écho dans la charge utile
                    # n'est établi par aucune documentation.
                    #
                    # Écrit AVANT de répondre : le webhook ne peut arriver
                    # qu'après que le client a payé, donc après cette ligne.
                    # Un second appel à la route écrase la référence — c'est
                    # voulu, la session la plus récente est celle que le client
                    # a sous les yeux ; l'ancienne reste rattrapée par
                    # `merchant_reference`, qui ne bouge pas. Les deux voies se
                    # couvrent l'une l'autre.
                    "    _c_ref = _connect()",
                    f"    _c_ref.execute('UPDATE \"{table}\" SET payment_ref = ? "
                    "WHERE id = ?', (str(session.get('id')), id))",
                    "    _c_ref.commit(); _c_ref.close()",
                ]
            lignes += [
                # POINT 95 APPLIQUÉ AU FIL : `montant_centimes` GARDE son nom.
                # Le renommer casserait le bouton « Payer » de tout projet
                # existant, pour un gain cosmétique — c'est le raisonnement
                # exact tenu pour `username`. Le contrat dit ce que le champ
                # CONTIENT (le montant dans l'unité mineure de la devise ; pour
                # une devise sans sous-unité comme le XOF, c'est le montant
                # lui-même), et `devise` + `montant` sont ajoutés à côté pour
                # qu'aucune interface n'ait plus à diviser par cent au hasard.
                "    return {'status': 'success', 'url': session.get('url'),",
                "            'session_id': session.get('id'), "
                "'montant_centimes': centimes,",
                f"            'devise': '{devise['code']}', 'montant': montant}}",
                "",
            ]
        lignes += [
            "@app.post('/paiement/webhook', tags=['Paiement'])",
            "async def paiement_webhook(request: Request):",
            f"    _exiger_cle_paiement('{secret_env}', {secret_var})",
            "    brut = await request.body()",
            f"    entete = request.headers.get('{entete_signature}', '')",
            f"    # Signature : t=<horodatage>,{schema_signature}=<hmac sha256 de \"t.corps\">.",
            "    # Sans cette vérification, n'importe qui marquerait n'importe",
            "    # quelle commande comme payée avec un simple curl.",
            "    horodatage, signatures = None, []",
            "    for morceau in entete.split(','):",
            "        cle, _, valeur = morceau.partition('=')",
            "        if cle.strip() == 't': horodatage = valeur.strip()",
            f"        elif cle.strip() == '{schema_signature}': signatures.append(valeur.strip())",
            "    if not horodatage or not signatures:",
            "        raise HTTPException(status_code=400, detail='Signature absente ou malformée.')",
            "    # POINT 91 : l'horodatage était LU pour vérifier la signature, mais",
            "    # jamais daté. Un appel signé capté une fois restait donc rejouable",
            "    # indéfiniment — c'est la parade que Stripe documente, et elle ne",
            "    # coûte que ces trois lignes. Tolérance de cinq minutes : au-delà,",
            "    # ce n'est plus un réseau lent, c'est un rejeu.",
            "    try:",
            "        _age = abs(datetime.datetime.now(datetime.timezone.utc).timestamp()",
            "                   - int(horodatage))",
            "    except ValueError:",
            "        raise HTTPException(status_code=400, detail='Horodatage de signature illisible.')",
            "    if _age > 300:",
            "        raise HTTPException(status_code=400, detail=(",
            "            'Signature expirée : cet appel a plus de cinq minutes.'))",
            f"    attendue = hmac.new({secret_var}.encode(),",
            "                        (horodatage + '.').encode() + brut, hashlib.sha256).hexdigest()",
            "    if not any(hmac.compare_digest(attendue, s) for s in signatures):",
            "        raise HTTPException(status_code=400, detail='Signature invalide.')",
            "    evenement = json.loads(brut or b'{}')",
        ]
        if prestataire == "fedapay":
            lignes += [
            "    # La clé `entity` est PROUVÉE : le plugin Odoo officiel de",
            "    # FedaPay (fedapay/fedapay-odoo, controllers/main.py) lit le",
            "    # corps brut du webhook et fait `data.get('entity', {})`. Ce",
            "    # qui reste non prouvé, c'est que `merchant_reference` soit",
            "    # RÉÉMIS dans cette charge utile — la documentation l'établit",
            "    # sur la transaction, jamais sur l'événement. D'où le repli",
            "    # ci-dessous par l'identifiant du prestataire, et le",
            "    # FAIL-CLOSED si aucune des deux voies ne reconnaît la ligne :",
            "    # un règlement non enregistré coûte un appel au support, le",
            "    # mauvais enregistrement marqué payé coûte de l'argent.",
            "    objet = (evenement.get('entity')",
            "             or (evenement.get('data') or {}).get('object') or {})",
            "    reference = (objet.get('merchant_reference')",
            "                 or (objet.get('custom_metadata') or {}).get('monl_reference')",
            "                 or '')",
            "    _type_evenement = evenement.get('name') or evenement.get('type')",
            "    _attendu = 'transaction.approved'",
            # REPLI PAR L'IDENTIFIANT DU PRESTATAIRE. C'est la voie que le
            # plugin Odoo officiel emploie (`notification_data.get('id')`
            # confronté à l'id mémorisé à la création) — la seule des deux qui
            # soit établie par du code en production plutôt que déduite. Elle
            # ne sert QUE si la référence qualifiée n'est pas revenue : quand
            # elle est là, rien n'est écrasé.
            "    if not str(reference).partition(':')[2].isdigit():",
            "        _ref_prestataire = str(objet.get('id') or '')",
            "        _repli = ''",
            "        if _ref_prestataire:",
            "            _c_lu = _connect(); _cur_lu = _c_lu.cursor()",
            "            try:",
            ]
            for entite in sorted(self.payable_by_entity):
                lignes += [
            f"                _cur_lu.execute('SELECT id FROM \"{entite.lower()}\" "
            "WHERE payment_ref = ?', (_ref_prestataire,))",
            "                _ligne_lu = _cur_lu.fetchone()",
            f"                if _ligne_lu and not _repli: _repli = '{entite}:' "
            "+ str(_ligne_lu[0])",
                ]
            lignes += [
            "            finally:",
            "                _c_lu.close()",
            "        if _repli:",
            "            reference = _repli",
            ]
        else:
            lignes += [
            "    objet = (evenement.get('data') or {}).get('object') or {}",
            "    reference = objet.get('client_reference_id') or ''",
            "    _type_evenement = evenement.get('type')",
            "    _attendu = 'checkout.session.completed'",
            ]
        lignes += [
            "    # La référence est 'EntiteQualifiee:id' (voir la création de session",
            "    # ci-dessus) : un id nu se confondrait avec celui d'une AUTRE entité",
            "    # payable de la même app, et marquerait payé le mauvais enregistrement.",
            "    entite_ref, _, id_texte = str(reference).partition(':')",
            "    if _type_evenement != _attendu or not id_texte.isdigit():",
            "        return {'status': 'ignored'}",
            "    id_cible = int(id_texte)",
            "    conn = _connect(); cursor = conn.cursor()",
            "    try:",
        ]
        for indice, entite in enumerate(sorted(self.payable_by_entity)):
            mot_cle = "if" if indice == 0 else "elif"
            lignes.append(f"        {mot_cle} entite_ref == '{entite}':")
            lignes.append(
                f"            cursor.execute('UPDATE \"{entite.lower()}\" SET payment_status = ?, "
                f"payment_ref = ? WHERE id = ?', ('payee', objet.get('id'), id_cible))")
        lignes += [
            "        conn.commit()",
            "    except Exception:",
            "        conn.rollback(); conn.close(); raise",
            "    conn.close()",
            "    return {'status': 'success'}",
            "",
        ]
        return lignes
