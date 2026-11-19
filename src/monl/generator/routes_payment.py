"""The two payment routes.

Three invariants never to loosen: the amount is read FROM THE DATABASE and
the route accepts NO body; the webhook signature is checked before any
write — it is the ONLY place in the generated backend where an
unauthenticated third party writes; a missing key gives 503 and NAMES it,
without preventing the rest of the server from working."""

class PaymentRoutesMixin:
    """The two payment routes."""

    # ─────────────────────────────────────────────────────────────────
    # PAYMENT BRICK (point 74). Two routes only, and one principle: the amount
    # charged comes from the DATABASE, never from the client. A cart that sends
    # its own price is a cart one can haggle over.
    #
    # Secrets come from the environment (same rule as the JWT secret). When
    # they are missing, the routes exist but answer 503 naming the missing
    # variable: a payment must refuse loudly, never fail silently — and the
    # smoke test stays green offline.
    # ─────────────────────────────────────────────────────────────────

    def _parameters_provider(self, provider, code_devise):
        """The webhook names, the key names and the prelude of a provider.

        Extracted from `_generate_payment_routes` (complexity ceiling); emitted
        text byte-identical. Returns (secret_var, secret_env, signature header,
        signature scheme, key_var, key_env, prelude lines)."""
        if provider == "fedapay":
            return ("FEDAPAY_WEBHOOK_SECRET", "MONL_FEDAPAY_WEBHOOK_SECRET",
                    "x-fedapay-signature", "s",
                    "FEDAPAY_SECRET_KEY", "MONL_FEDAPAY_SECRET_KEY",
                    self._prelude_fedapay(code_devise.upper()))
        return ("STRIPE_WEBHOOK_SECRET", "STRIPE_WEBHOOK_SECRET",
                "stripe-signature", "v1",
                "STRIPE_SECRET_KEY", "STRIPE_SECRET_KEY",
                self._prelude_stripe())

    def _prelude_stripe(self):
        """The Stripe prelude: keys, overridable endpoint, checkout session."""
        return [
            "",
            "# ── Payment ('payable' brick) ─────────────────────────────────",
            "STRIPE_SECRET_KEY = (os.environ.get('STRIPE_SECRET_KEY') or '').strip()",
            "STRIPE_WEBHOOK_SECRET = (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip()",
            "# Overridable endpoint: essential to exercise the full flow",
            "# without calling Stripe (see tests).",
            "STRIPE_BASE_URL = (os.environ.get('MONL_STRIPE_BASE_URL')",
            "                   or 'https://api.stripe.com').rstrip('/')",
            "",
            "def _exiger_cle_paiement(nom, valeur):",
            "    if not valeur:",
            "        raise HTTPException(status_code=503, detail=(",
            "            f'Payment unavailable: the environment variable {nom} is not set '",
            "            'on the server. No payment can be accepted while it is '",
            "            'missing.'))",
            "",
            "def _session_paiement(montant_centimes, devise, reference, retour):",
            "    \"\"\"Creates a checkout session. The amount is in CENTS,",
            "    calculated server-side from the database.\"\"\"",
            "    corps = urllib.parse.urlencode({",
            "        'mode': 'payment',",
            "        'success_url': retour + '?paiement=ok',",
            "        'cancel_url': retour + '?paiement=annule',",
            "        'client_reference_id': str(reference),",
            "        'line_items[0][quantity]': '1',",
            "        'line_items[0][price_data][currency]': devise,",
            "        'line_items[0][price_data][unit_amount]': str(montant_centimes),",
            "        'line_items[0][price_data][product_data][name]': f'Order {reference}',",
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
            "            f'The payment provider refused the request ({e.code}): {detail}'))",
            "    except urllib.error.URLError as e:",
            "        raise HTTPException(status_code=502, detail=(",
            "            f'Payment provider unreachable: {e.reason}'))",
            "",
        ]


    def _generate_payment_routes(self):
        if not self.payable_by_entity:
            return []
        # BRICK 2a: the currency comes from the validator ALREADY resolved into
        # {code, exponent}; here we only read it. The default is applied only
        # in this place — not in the validator — so that a silent spec keeps
        # producing exactly what it produced (`payment_currency is None` ⇒ EUR,
        # exponent 2 ⇒ ×100 as before).
        devise = self.payment_currency or {"code": "EUR", "exponent": 2}
        code_devise = devise["code"].lower()
        exponent_currency = devise["exponent"]
        # BRICK 2b: the provider. `None` ⇒ Stripe, and the Stripe emission is
        # left byte-for-byte INTACT — the condition for no existing project to
        # see its app.py move. FedaPay is a SECOND emission, not a
        # generalization of the first: what is factored out is the security
        # core (amount read from the database, signature checked before any
        # write, 503 naming the variable, qualified reference), not the wire
        # format.
        provider = self.payment_provider or "stripe"
        # What DIFFERS from one provider to another at the webhook: the
        # secret's name, the header, and the letter of the signature scheme.
        # The rest — the HMAC-SHA256 of "timestamp.raw body", the five-minute
        # tolerance, the check BEFORE any write — is identical, and that is
        # precisely what gets factored out. The FedaPay recipe was reread in
        # its official SDK (Webhook.ts: EXPECTED_SCHEME = 's',
        # `${timestamp}.${payload}`, sha256 hex, DEFAULT_TOLERANCE = 300),
        # never inferred from prose.
        (secret_var, secret_env, header_signature, schema_signature,
         key_var, key_env, lines) = self._parameters_provider(
            provider, code_devise)
        for entity, field in sorted(self.payable_by_entity.items()):
            table = entity.lower()
            # POINT 99: the column compared with `current_user_id` must carry
            # an ACCOUNT identifier — hence the one from
            # `_identity_fk_columns`, not the first incoming relation that
            # comes along. On a child entity of a business table, that first
            # relation carries the id of a catalog row: the comparison would
            # have been wrong both ways (the owner can no longer pay, a
            # stranger can if the two identifiers coincide). The validator now
            # refuses this case; the assertion below guarantees that no
            # divergence between it and this line can write a route without a
            # check.
            columns_account = self._identity_fk_columns().get(entity, set())
            owner = ({"fk_column": sorted(columns_account)[0]}
                       if columns_account else None)
            # POINT 87: under TRANSITIVE ownership, the entity's foreign key
            # designates the intermediate, not an account — which is why point
            # 81 refused to charge here. A one-level join gives the ACCOUNT id,
            # so the comparison that follows is identical to the direct case:
            # nothing else changes in this route.
            #
            # The invariant NOT to break: the amount, the state and the owner
            # come out of the SAME read. Two separate queries would reopen the
            # window between the access check and the amount calculation — so
            # the join goes INTO the SELECT, it is not added beside it.
            chaine = self._transitive_chain(entity)
            if not chaine and not owner:
                # POINT 99: without an owner, the route would charge any record
                # for any authenticated caller (IDOR). The validator forbids it
                # — reaching here means it has diverged from this layer.
                # Failing at generation is better than writing a payment route
                # without access control, same reasoning as `plan_derivations`.
                raise ValueError(
                    f"Generation: '{entity}' is 'payable' but no column carries "
                    f"the owning account's identifier — the payment route could "
                    f"answer 403 to nobody.")
            if chaine:
                # Bricks 11 and 24: a chain of JOINs, one per link, up to the
                # account. Amount, state and owner come out of the SAME read.
                _from, _cur, _fk = self._chain_join(entity)
                columns = f't."{field}", t.payment_status, {_cur}."{_fk}"'
                from_ = _from
            else:
                columns = (f'"{field}", payment_status, "{owner["fk_column"]}"')
                from_ = f'"{table}"'
            lines += [
                f"@app.post('/{table}/{{id}}/paiement', tags=['Paiement'])",
                f"def payer_{table}(id: int, request: Request, "
                "current_user_id: int = Depends(get_current_user_id)):",
                f"    _exiger_cle_paiement('{key_env}', {key_var})",
                "    conn = _connect(); cursor = conn.cursor()",
                f"    cursor.execute('SELECT {columns} FROM {from_} WHERE "
                f"{'t.' if chaine else ''}id = ?', (id,))",
                "    ligne = cursor.fetchone()",
                "    conn.close()",
                # Under a join, an ORPHAN row (intermediate gone) gives no
                # result: it belongs to nobody, and 404 is the right answer —
                # certainly not "payable by anyone".
                "    if not ligne:",
                "        raise HTTPException(status_code=404, detail='Not found.')",
            ]
            lines += [
                "    montant, etat, proprietaire = ligne",
                "    if proprietaire is not None and proprietaire != current_user_id:",
                "        raise HTTPException(status_code=403, detail="
                "'This record does not belong to you.')",
            ]
            lines += [
                "    if etat == 'payee':",
                "        raise HTTPException(status_code=409, detail='Already paid.')",
                # BRICK 2a: the provider expects an INTEGER in the currency's
                # minor unit, hence `amount × 10**exponent`. The fixed `×100`
                # from before was right for the euro and wrong everywhere else:
                # the CFA franc has no subunit, an order of 5,000 FCFA would
                # have gone out as 500,000. The variable keeps the name
                # `centimes` — it is the code's word, not the wire's (see
                # below).
                "    centimes = int(round(float(montant or 0) * "
                f"{10 ** exponent_currency}))",
                "    if centimes <= 0:",
                "        raise HTTPException(status_code=400, detail=(",
                "            'Zero or negative amount: nothing to charge.'))",
                "    retour = str(request.base_url).rstrip('/') + '/site/'",
                # SECURITY FIX: the reference now carries the entity name. A
                # plain numeric id was confused with that of ANOTHER payable
                # entity in the same app -- the webhook then marked as paid a
                # record from a completely different table, which merely had
                # the same id.
                f"    reference = '{entity}:' + str(id)",
                f"    session = _session_paiement(centimes, '{code_devise}', "
                "reference, retour)",
            ]
            if provider == "fedapay":
                lines += [
                    # PROVEN, NOT GUESSED: FedaPay's official Odoo plugin
                    # (fedapay/fedapay-odoo, payment_transaction.py) finds its
                    # order through `notification_data.get('id')`, the
                    # transaction id it stored at creation. We therefore store
                    # the same one, which gives the webhook a second way to
                    # recognize the record — independent of
                    # `merchant_reference`, whose echo in the payload is
                    # established by no documentation.
                    #
                    # Written BEFORE answering: the webhook can only arrive
                    # after the client has paid, hence after this line. A
                    # second call to the route overwrites the reference — on
                    # purpose, the most recent session is the one the client
                    # has in front of them; the old one is still caught by
                    # `merchant_reference`, which does not change. The two
                    # paths cover each other.
                    "    _c_ref = _connect()",
                    f"    _c_ref.execute('UPDATE \"{table}\" SET payment_ref = ? "
                    "WHERE id = ?', (str(session.get('id')), id))",
                    "    _c_ref.commit(); _c_ref.close()",
                ]
            lines += [
                # POINT 95 APPLIED TO THE WIRE: `montant_centimes` KEEPS its
                # name. Renaming it would break the "Pay" button of every
                # existing project for a cosmetic gain — exactly the reasoning
                # held for `username`. The contract says what the field
                # CONTAINS (the amount in the currency's minor unit; for a
                # currency without a subunit such as XOF, it is the amount
                # itself), and `devise` + `montant` are added beside it so that
                # no interface has to divide by a hundred at random anymore.
                "    return {'status': 'success', 'url': session.get('url'),",
                "            'session_id': session.get('id'), "
                "'montant_centimes': centimes,",
                f"            'devise': '{devise['code']}', 'montant': montant}}",
                "",
            ]
        lines += [
            "WEBHOOK_MAX_BYTES = 256 * 1024",
            "",
            "@app.post('/paiement/webhook', tags=['Paiement'])",
            "async def paiement_webhook(request: Request):",
            f"    _exiger_cle_paiement('{secret_env}', {secret_var})",
            "    _taille_annoncee = request.headers.get('content-length')",
            "    try:",
            "        _taille_annoncee = int(_taille_annoncee) if _taille_annoncee is not None else None",
            "    except ValueError:",
            "        _taille_annoncee = None",
            "    if _taille_annoncee is not None and _taille_annoncee > WEBHOOK_MAX_BYTES:",
            "        raise HTTPException(status_code=413, detail='Webhook too large.')",
            "    _blocs, _taille = [], 0",
            "    async for _bloc in request.stream():",
            "        _taille += len(_bloc)",
            "        if _taille > WEBHOOK_MAX_BYTES:",
            "            raise HTTPException(status_code=413, detail='Webhook too large.')",
            "        _blocs.append(_bloc)",
            "    brut = b''.join(_blocs)",
            f"    entete = request.headers.get('{header_signature}', '')",
            f"    # Signature: t=<timestamp>,{schema_signature}=<hmac sha256 of \"t.body\">.",
            "    # Without this check, anyone could mark any order as paid",
            "    # with a plain curl.",
            "    horodatage, signatures = None, []",
            "    for morceau in entete.split(','):",
            "        cle, _, valeur = morceau.partition('=')",
            "        if cle.strip() == 't': horodatage = valeur.strip()",
            f"        elif cle.strip() == '{schema_signature}': signatures.append(valeur.strip())",
            "    if not horodatage or not signatures:",
            "        raise HTTPException(status_code=400, detail='Missing or malformed signature.')",
            "    # POINT 91: the timestamp was READ to check the signature, but never",
            "    # dated. A signed call captured once stayed replayable forever —",
            "    # this is the defense Stripe documents, and it costs only these",
            "    # three lines. Five minutes of tolerance: beyond that it is no",
            "    # longer a slow network, it is a replay.",
            "    try:",
            "        _age = abs(datetime.datetime.now(datetime.timezone.utc).timestamp()",
            "                   - int(horodatage))",
            "    except ValueError:",
            "        raise HTTPException(status_code=400, detail='Unreadable signature timestamp.')",
            "    if _age > 300:",
            "        raise HTTPException(status_code=400, detail=(",
            "            'Expired signature: this call is more than five minutes old.'))",
            f"    attendue = hmac.new({secret_var}.encode(),",
            "                        (horodatage + '.').encode() + brut, hashlib.sha256).hexdigest()",
            "    if not any(hmac.compare_digest(attendue, s) for s in signatures):",
            "        raise HTTPException(status_code=400, detail='Invalid signature.')",
            "    evenement = json.loads(brut or b'{}')",
        ]
        if provider == "fedapay":
            lines += [
            "    # The `entity` key is PROVEN: FedaPay's official Odoo plugin",
            "    # (fedapay/fedapay-odoo, controllers/main.py) reads the raw",
            "    # webhook body and does `data.get('entity', {})`. What remains",
            "    # unproven is that `merchant_reference` is SENT BACK in this",
            "    # payload — the documentation establishes it on the transaction,",
            "    # never on the event. Hence the fallback below on the provider's",
            "    # identifier, and FAIL-CLOSED if neither path recognizes the row:",
            "    # an unrecorded payment costs a support call, the wrong record",
            "    # marked paid costs money.",
            "    objet = (evenement.get('entity')",
            "             or (evenement.get('data') or {}).get('object') or {})",
            "    reference = (objet.get('merchant_reference')",
            "                 or (objet.get('custom_metadata') or {}).get('monl_reference')",
            "                 or '')",
            "    _type_evenement = evenement.get('name') or evenement.get('type')",
            "    _attendu = 'transaction.approved'",
            # FALLBACK THROUGH THE PROVIDER'S IDENTIFIER. It is the path the
            # official Odoo plugin uses (`notification_data.get('id')` matched
            # against the id stored at creation) — the only one of the two
            # established by code in production rather than inferred. It serves
            # ONLY if the qualified reference did not come back: when it is
            # there, nothing is overwritten.
            "    if not str(reference).partition(':')[2].isdigit():",
            "        _ref_prestataire = str(objet.get('id') or '')",
            "        _repli = ''",
            "        if _ref_prestataire:",
            "            _c_lu = _connect(); _cur_lu = _c_lu.cursor()",
            "            try:",
            ]
            for entity in sorted(self.payable_by_entity):
                lines += [
            f"                _cur_lu.execute('SELECT id FROM \"{entity.lower()}\" "
            "WHERE payment_ref = ?', (_ref_prestataire,))",
            "                _ligne_lu = _cur_lu.fetchone()",
            f"                if _ligne_lu and not _repli: _repli = '{entity}:' "
            "+ str(_ligne_lu[0])",
                ]
            lines += [
            "            finally:",
            "                _c_lu.close()",
            "        if _repli:",
            "            reference = _repli",
            ]
        else:
            lines += [
            "    objet = (evenement.get('data') or {}).get('object') or {}",
            "    reference = objet.get('client_reference_id') or ''",
            "    _type_evenement = evenement.get('type')",
            "    _attendu = 'checkout.session.completed'",
            ]
        lines += [
            "    # The reference is 'QualifiedEntity:id' (see session creation",
            "    # above): a bare id would be confused with one of ANOTHER payable",
            "    # entity of the same app, and would mark the wrong record paid.",
            "    entite_ref, _, id_texte = str(reference).partition(':')",
            "    if _type_evenement != _attendu or not id_texte.isdigit():",
            "        return {'status': 'ignored'}",
            "    id_cible = int(id_texte)",
            "    conn = _connect(); cursor = conn.cursor()",
            "    try:",
        ]
        for index, entity in enumerate(sorted(self.payable_by_entity)):
            word_key = "if" if index == 0 else "elif"
            lines.append(f"        {word_key} entite_ref == '{entity}':")
            lines.append(
                f"            cursor.execute('UPDATE \"{entity.lower()}\" SET payment_status = ?, "
                f"payment_ref = ? WHERE id = ?', ('payee', objet.get('id'), id_cible))")
        lines += [
            "        conn.commit()",
            "    except Exception:",
            "        conn.rollback(); conn.close(); raise",
            "    conn.close()",
            "    return {'status': 'success'}",
            "",
        ]
        return lines
