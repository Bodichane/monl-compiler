"""What depends on the provider, and what comes AFTER payment.

`writableAfterPayment` (point 113): a dedicated route, reserved to the
named actor, without touching the generic `Update` lock, which stays
absolute."""

from . import sql


class PrestatairesRoutesMixin:
    """What depends on the provider, and what comes AFTER payment."""

    # ─────────────────────────────────────────────────────────────────
    # BRICK 2b — FedaPay. Stripe does not operate in West Africa, where money
    # goes through mobile money (MTN MoMo, Moov, Wave) behind an aggregator.
    #
    # TWO calls where Stripe makes one: `POST /v1/transactions` returns an
    # `id`, then `POST /v1/transactions/{id}/token` returns the payment `url`.
    # Creation alone gives NO URL — stopping there would ship a "Pay" button
    # that leads nowhere.
    #
    # The invariants of points 74, 75 and 91 hold identically: the amount is
    # the one read from the database and passed by the sole caller, the
    # reference is qualified by the entity, a missing key gives 503 and names
    # it.
    # ─────────────────────────────────────────────────────────────────
    def _prelude_fedapay(self, code_devise):
        return [
            "",
            "# ── Payment ('payable' brick, FedaPay provider) ─────────────",
            "FEDAPAY_SECRET_KEY = (os.environ.get('MONL_FEDAPAY_SECRET_KEY') or '').strip()",
            "FEDAPAY_WEBHOOK_SECRET = (os.environ.get('MONL_FEDAPAY_WEBHOOK_SECRET') or '').strip()",
            "# Sandbox by default: a test key and a production endpoint never",
            "# go together, and the cheapest default when something is wrong",
            "# is the one that charges no real money. Going to production is",
            "# an EXPLICIT act.",
            "FEDAPAY_BASE_URL = (os.environ.get('MONL_FEDAPAY_BASE_URL')",
            "                    or 'https://sandbox-api.fedapay.com').rstrip('/')",
            "",
            "def _exiger_cle_paiement(nom, valeur):",
            "    if not valeur:",
            "        raise HTTPException(status_code=503, detail=(",
            "            f'Payment unavailable: the environment variable {nom} is not set '",
            "            'on the server. No payment can be accepted while it is '",
            "            'missing.'))",
            "",
            "def _appel_fedapay(chemin, corps=None):",
            "    donnees = json.dumps(corps).encode() if corps is not None else b''",
            "    requete = urllib.request.Request(",
            "        FEDAPAY_BASE_URL + chemin, data=donnees, method='POST')",
            "    requete.add_header('Authorization', 'Bearer ' + FEDAPAY_SECRET_KEY)",
            "    requete.add_header('Content-Type', 'application/json')",
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
            "def _session_paiement(montant_centimes, devise, reference, retour):",
            "    \"\"\"Creates a FedaPay transaction, then its payment link.",
            "",
            "    The amount arrives ALREADY converted to the currency's minor",
            "    unit (brick 2a) and comes from the database, never the client.",
            "    \"\"\"",
            "    transaction = _appel_fedapay('/v1/transactions', {",
            "        'description': f'Order {reference}',",
            "        'amount': int(montant_centimes),",
            f"        'currency': {{'iso': '{code_devise}'}},",
            "        'callback_url': retour + '?paiement=retour',",
            "        # The qualified 'Entity:id' reference (point 75) is sent in",
            "        # BOTH fields FedaPay documents for it: the webhook does not",
            "        # expose the same one depending on the version, and filling",
            "        # only one would be betting on which.",
            "        'merchant_reference': str(reference),",
            "        'custom_metadata': {'monl_reference': str(reference)},",
            "    })",
            "    objet = transaction.get('v1/transaction') or transaction.get('transaction') or transaction",
            "    identifiant = objet.get('id')",
            "    if not identifiant:",
            "        raise HTTPException(status_code=502, detail=(",
            "            'The provider returned no transaction identifier.'))",
            "    jeton = _appel_fedapay(f'/v1/transactions/{identifiant}/token')",
            "    url = jeton.get('url')",
            "    if not url:",
            "        raise HTTPException(status_code=502, detail=(",
            "            'The provider returned no payment URL.'))",
            "    # Same return shape as the Stripe path: the payment route is",
            "    # shared and does not know the provider.",
            "    return {'url': url, 'id': identifiant}",
            "",
        ]

    def _lignes_bascule_apres_paiement(self, entite, config, table):
        """Releasing an effect from the post-payment route (brick 20).

        The field targeted by `releases` can belong to THIS route rather than to
        the generic Update: it is then here that a status reaches its releasing
        value, so here that the stock must come back.

        Two differences from the generic route, both due to this route's schema
        where fields are OPTIONAL. The reactivation guard requires `is not None`:
        without it, a call that only touches the tracking number would refuse the
        cancelled order it does not change. And the transition only counts if the
        field is actually supplied."""
        lignes = []
        for regle in self.release_rules_by_entity.get(entite, []):
            if regle["field"] not in config["fields"]:
                continue  # the generic Update keeps this field, and its transition
            enfant = regle["releases"]
            fk_enfant = self._fk_enfant_libere(entite, enfant)
            if not fk_enfant:
                continue
            champ, valeur = regle["field"], regle["value"]
            lignes += [
                f"    cursor.execute('SELECT \"{champ}\" FROM "
                f'"{table}" WHERE id = ?\', (id,))',
                "    _etat_avant = cursor.fetchone()",
                # The released state is TERMINAL: what was returned is no
                # longer guaranteed available, and reopening the order would
                # give free stock — the point 77 family.
                f"    if (_etat_avant and _etat_avant[0] == {valeur!r}",
                f"            and data.{champ} is not None "
                f"and data.{champ} != {valeur!r}):",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            \"This record is {valeur}: what it had "
                f"consumed has been returned, \"",
                "            'and nothing guarantees it is still available. "
                "Create a new one.'))",
                f"    _bascule = (_etat_avant and _etat_avant[0] != {valeur!r}",
                f"                and data.{champ} == {valeur!r})",
                "    if _bascule:",
            ]
            lignes += self._lignes_restitution(enfant, fk_enfant, indent="        ")
        return lignes

    def _ligne_schema_apres_paiement(self, entite, field):
        """The Pydantic line of a post-payment route field: type, choice list,
        declared bounds and length ceiling. Extracted from
        `_generate_postpayment_routes` (complexity ceiling); emitted text
        byte-identical."""
        field_type = self.entities[entite][field]
        py_type = {"Integer": "int", "Float": "float", "Money": "float",
                   "Boolean": "bool"}.get(field_type, "str")
        choix = self.enumerated_fields.get(entite, {}).get(field)
        if choix:
            valeurs = ", ".join(repr(v) for v in choix)
            py_type = f"Literal[{valeurs}]"
        contraintes = self.field_constraints.get(entite, {}).get(field, {})
        bornes = []
        for nom, mot_texte, mot_nombre in (("min", "min_length", "ge"),
                                            ("max", "max_length", "le")):
            borne = contraintes.get(nom)
            if borne:
                mot = mot_texte if borne["portee"] == "longueur" else mot_nombre
                bornes.append(f"{mot}={borne['valeur']}")
        if py_type == "str":
            limite = {"Text": 20000, "Email": 320, "UUID": 36}.get(
                field_type, 255)
            if not any(b.startswith("max_length=") for b in bornes):
                bornes.append(f"max_length={limite}")
            if field_type == "Email":
                bornes.append(r"pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'")
            if field_type == "UUID":
                bornes.append(
                    r"pattern=r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'")
        if bornes and not choix:
            return f"    {field}: Optional[{py_type}] = Field(None, {', '.join(bornes)})"
        return f"    {field}: Optional[{py_type}] = None"

    def _generate_postpayment_routes(self):
        lignes = []
        for entite, config in sorted(self.postpayment_writable_by_entity.items()):
            table = entite.lower()
            schema = f"{entite}ApresPaiementSchema"
            lignes += ["", f"class {schema}(BaseModel):"]
            for field in config["fields"]:
                lignes.append(self._ligne_schema_apres_paiement(entite, field))

            lignes.extend(self._required_text_validator(entite, config["fields"]))

            existence = sql.cat(
                sql.kw("SELECT id, "), sql.ident("payment_status"),
                sql.kw(" FROM "), sql.ident(table),
                sql.kw(" WHERE id = "), sql.bind("id"))
            existence_sql, existence_params = sql.execute_args(existence)
            lignes += [
                "",
                f"@app.put('/{table}/{{id}}/apres-paiement', tags=['Paiement'])",
                f"def modifier_{table}_apres_paiement(id: int, data: {schema}, "
                "current_actor: str = Depends(verify_jwt_and_get_actor)):",
                f"    if current_actor != {config['actor']!r}:",
                "        raise HTTPException(status_code=403, detail=(",
                "            \"Access control: only the resource's parties \"",
                "            'can perform this action'))",
                "    conn = _connect(); cursor = conn.cursor()",
                f"    cursor.execute({existence_sql}, {existence_params})",
                "    enregistrement = cursor.fetchone()",
                "    if not enregistrement:",
                "        conn.close()",
                "        raise HTTPException(status_code=404, detail='Record not found')",
                "    if enregistrement[1] != 'payee':",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                "            'Action available only after the payment is confirmed'))",
            ]
            # BRICK 20 on a field this route has reserved for itself. When
            # `writableAfterPayment` takes the field of a `releases` rule, it
            # removes it from the generic Update schema: the transition must
            # therefore live HERE, otherwise cancelling a PAID order would
            # never return its stock — a silent loss, worse than the 500 being
            # fixed.
            lignes += self._lignes_bascule_apres_paiement(entite, config, table)
            for field in config["fields"]:
                update = sql.cat(
                    sql.kw("UPDATE "), sql.ident(table), sql.kw(" SET "),
                    sql.ident(field), sql.kw(" = "), sql.bind(f"data.{field}"),
                    sql.kw(" WHERE id = "), sql.bind("id"))
                update_sql, update_params = sql.execute_args(update)
                lignes += [
                    f"    if data.{field} is not None:",
                    f"        cursor.execute({update_sql}, {update_params})",
                ]
            lignes += [
                "    conn.commit(); conn.close()",
                "    return {'status': 'success', 'id': id}",
                "",
            ]
        return lignes
