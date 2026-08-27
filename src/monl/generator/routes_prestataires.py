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
            "# ── Paiement (brique 'payable', prestataire FedaPay) ─────────",
            "FEDAPAY_SECRET_KEY = (os.environ.get('MONL_FEDAPAY_SECRET_KEY') or '').strip()",
            "FEDAPAY_WEBHOOK_SECRET = (os.environ.get('MONL_FEDAPAY_WEBHOOK_SECRET') or '').strip()",
            "# Bac à sable par défaut : une clé de test et un point de",
            "# terminaison de production ne vont jamais ensemble, et le défaut",
            "# le moins coûteux en cas d'erreur est celui qui n'encaisse pas de",
            "# vrai argent. Le passage en production est un geste EXPLICITE.",
            "FEDAPAY_BASE_URL = (os.environ.get('MONL_FEDAPAY_BASE_URL')",
            "                    or 'https://sandbox-api.fedapay.com').rstrip('/')",
            "",
            "def _exiger_cle_paiement(nom, valeur):",
            "    if not valeur:",
            "        raise HTTPException(status_code=503, detail=(",
            "            f\"Paiement indisponible : la variable d'environnement {nom} n'est pas \"",
            "            'définie sur le serveur. Aucun règlement ne peut être accepté tant '",
            "            \"qu'elle manque.\"))",
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
            "            f'Le prestataire de paiement a refusé la demande ({e.code}) : {detail}'))",
            "    except urllib.error.URLError as e:",
            "        raise HTTPException(status_code=502, detail=(",
            "            f'Prestataire de paiement injoignable : {e.reason}'))",
            "",
            "def _session_paiement(montant_centimes, devise, reference, retour):",
            "    \"\"\"Crée une transaction FedaPay puis son lien de paiement.",
            "",
            "    Le montant arrive DÉJÀ converti dans l'unité mineure de la",
            "    devise (brique 2a) et vient de la base, jamais du client.",
            "    \"\"\"",
            "    transaction = _appel_fedapay('/v1/transactions', {",
            "        'description': f'Commande {reference}',",
            "        'amount': int(montant_centimes),",
            f"        'currency': {{'iso': '{code_devise}'}},",
            "        'callback_url': retour + '?paiement=retour',",
            "        # La référence qualifiée 'Entite:id' (point 75) est envoyée",
            "        # dans les DEUX champs que FedaPay documente pour cela : le",
            "        # webhook n'expose pas le même selon la version, et en",
            "        # renseigner un seul reviendrait à parier sur laquelle.",
            "        'merchant_reference': str(reference),",
            "        'custom_metadata': {'monl_reference': str(reference)},",
            "    })",
            "    objet = transaction.get('v1/transaction') or transaction.get('transaction') or transaction",
            "    identifiant = objet.get('id')",
            "    if not identifiant:",
            "        raise HTTPException(status_code=502, detail=(",
            "            \"Le prestataire n'a pas renvoyé d'identifiant de transaction.\"))",
            "    jeton = _appel_fedapay(f'/v1/transactions/{identifiant}/token')",
            "    url = jeton.get('url')",
            "    if not url:",
            "        raise HTTPException(status_code=502, detail=(",
            "            \"Le prestataire n'a pas renvoyé d'URL de paiement.\"))",
            "    # Même forme de retour que la voie Stripe : la route de règlement",
            "    # est commune et ne connaît pas le prestataire.",
            "    return {'url': url, 'id': identifiant}",
            "",
        ]

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
                "            \"Contrôle d'accès : seules les parties de la ressource \"",
                "            'peuvent exécuter cette action'))",
                "    conn = _connect(); cursor = conn.cursor()",
                f"    cursor.execute({existence_sql}, {existence_params})",
                "    enregistrement = cursor.fetchone()",
                "    if not enregistrement:",
                "        conn.close()",
                "        raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                "    if enregistrement[1] != 'payee':",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                "            'Action disponible uniquement après confirmation du paiement'))",
            ]
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
