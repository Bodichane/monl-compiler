"""Ce qui dépend du prestataire, et ce qui vient APRÈS le règlement.

`writableAfterPayment` (point 113) : route dédiée, réservée à l'acteur
nommé, sans toucher au verrou générique d'`Update` qui reste absolu."""

from . import sql


class PrestatairesRoutesMixin:
    """Ce qui dépend du prestataire, et ce qui vient APRÈS le règlement."""

    # ─────────────────────────────────────────────────────────────────
    # BRIQUE 2b — FedaPay. Stripe n'opère pas en Afrique de l'Ouest, où
    # l'argent passe par le mobile money (MTN MoMo, Moov, Wave) derrière un
    # agrégateur.
    #
    # DEUX appels là où Stripe en fait un : `POST /v1/transactions` rend un
    # `id`, puis `POST /v1/transactions/{id}/token` rend l'`url` de paiement.
    # La création seule ne donne AUCUNE URL — s'arrêter là livrerait un bouton
    # « Payer » qui ne mène nulle part.
    #
    # Les invariants des points 74, 75 et 91 sont tenus à l'identique : le
    # montant est celui lu en base et passé par le seul appelant, la référence
    # est qualifiée par l'entité, la clé absente donne 503 en la nommant.
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
        """Libération d'un effet depuis la route après-paiement (brique 20).

        Le champ visé par `releases` peut appartenir à CETTE route et non à
        l'Update générique : c'est alors ici qu'un statut atteint sa valeur
        libératrice, donc ici que le stock doit revenir.

        Deux différences avec la route générique, toutes deux dues au schéma
        de cette route où les champs sont FACULTATIFS. La garde de
        réactivation exige `is not None` : sans elle, un appel qui ne touche
        qu'au numéro de suivi refuserait la commande annulée qu'il ne modifie
        pas. Et la bascule ne vaut que si le champ est réellement fourni.
        """
        lignes = []
        for regle in self.release_rules_by_entity.get(entite, []):
            if regle["field"] not in config["fields"]:
                continue  # l'Update générique garde ce champ, et sa bascule
            enfant = regle["releases"]
            fk_enfant = self._fk_enfant_libere(entite, enfant)
            if not fk_enfant:
                continue
            champ, valeur = regle["field"], regle["value"]
            lignes += [
                f"    cursor.execute('SELECT \"{champ}\" FROM "
                f'"{table}" WHERE id = ?\', (id,))',
                "    _etat_avant = cursor.fetchone()",
                # L'état libéré est TERMINAL : ce qui a été rendu n'est plus
                # garanti disponible, et reprendre la commande donnerait du
                # stock gratuit — famille du point 77.
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

    def _generate_postpayment_routes(self):
        lignes = []
        for entite, config in sorted(self.postpayment_writable_by_entity.items()):
            table = entite.lower()
            schema = f"{entite}ApresPaiementSchema"
            lignes += ["", f"class {schema}(BaseModel):"]
            for field in config["fields"]:
                field_type = self.entities[entite][field]
                py_type = "str"
                if field_type == "Integer":
                    py_type = "int"
                elif field_type in ("Float", "Money"):
                    py_type = "float"
                elif field_type == "Boolean":
                    py_type = "bool"
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
                    lignes.append(
                        f"    {field}: Optional[{py_type}] = Field(None, {', '.join(bornes)})")
                else:
                    lignes.append(f"    {field}: Optional[{py_type}] = None")

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
            # BRIQUE 20 sur un champ que cette route s'est réservé. Quand
            # `writableAfterPayment` prend le champ d'une règle `releases`, il
            # le retire du schéma de l'Update générique : la bascule doit donc
            # vivre ICI, sinon annuler une commande PAYÉE ne rendrait jamais
            # son stock — une perte silencieuse, pire que le 500 qu'on répare.
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
