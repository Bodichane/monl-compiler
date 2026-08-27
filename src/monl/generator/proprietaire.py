"""À QUI appartient une ligne — directement, ou par une chaîne.

`_transitive_chain` et `_owner_lookup_sql` sont la source UNIQUE de la
jointure de propriété (briques 11 et 24) : ne pas la réécrire ailleurs.
POINT 99 : `_identity_fk_columns` tranche entre une clé étrangère qui
désigne le registre des COMPTES et une qui désigne une table métier — et
seuls les parents ACTEURS sont candidats."""

from . import sql


class ProprietaireMixin:
    """À QUI appartient une ligne — directement, ou par une chaîne."""

    def _fk_to(self, child, parent):
        """Colonne de clé étrangère sur 'child' qui désigne 'parent'.

        Même convention et même garde que _derived_source_fk : si la colonne
        manque, la validation et le placement des clés étrangères ont divergé —
        et écrire une jointure sur None rendrait tout visible à tous."""
        for p in self._compute_fk_placements().get(child, []):
            if p["owner_entity"] == parent:
                return p["fk_column"]
        raise ValueError(
            f"Génération : aucune colonne de clé étrangère de '{child}' ne désigne "
            f"'{parent}', alors que le validateur exigeait cette relation pour une "
            f"chaîne de propriété transitive."
        )

    def _transitive_chain(self, entity):
        """Chaîne de propriété transitive de 'entity', ou None (briques 11 et 24).

        Retourne ce qu'il faut pour TOUTES les jointures de contrôle d'accès,
        quelle que soit la profondeur : l'acteur au bout de la chaîne, la
        colonne qui, sur le DERNIER maillon, porte l'identifiant du compte
        propriétaire ('actor_fk'), et la liste 'hops' des maillons, de bas en
        haut, chacun avec sa table et la colonne de clé étrangère qui, sur le
        niveau juste dessous, désigne ce maillon :
          - hops[0].ref : sur 'entity', pointe vers hops[0].table ;
          - hops[i].ref : sur hops[i-1].table, pointe vers hops[i].table.
        Source unique de vérité de la brique : routes, schémas et contrat
        frontend passent tous par ici."""
        chaine = self.transitive_ownership.get(entity)
        if not chaine:
            return None
        hops_raw = chaine["chain"]
        acteur = chaine["actor"]
        if not hops_raw:
            raise ValueError(
                f"Génération : '{entity}' est en propriété transitive mais sa chaîne "
                f"est vide -- le validateur a divergé. Echec plutôt que jointure "
                f"sur rien."
            )
        # Maillon du bas : la clé étrangère sur 'entity' vers le premier maillon.
        hop_bas = {"table": hops_raw[0].lower(),
                   "ref": self._fk_to(entity, hops_raw[0])}
        hops = [hop_bas]
        for i in range(1, len(hops_raw)):
            hops.append({"table": hops_raw[i].lower(),
                         "ref": self._fk_to(hops_raw[i - 1], hops_raw[i])})
        actor_fk = self._fk_to(hops_raw[-1], acteur)
        return {"via": hops_raw[0], "via_fk": hop_bas["ref"],
                "via_table": hop_bas["table"], "actor": acteur,
                "actor_fk": actor_fk, "hops": hops, "len": len(hops)}

    def _chain_read_where(self, entity, actor_frag):
        """Fragment SQL 'WHERE' (objet sql.Sql) qui borne 'entity' aux lignes du
        compte courant. 'actor_frag' est la valeur du compte, liée par sql.bind
        — jamais un fragment de texte.

        Sous chaîne à un ou plusieurs maillons, un 'IN' imbriqué par maillon :
        la colonne de clé étrangère du niveau courant est comparée aux
        identifiants du maillon suivant, jusqu'au maillon final filtré par
        'actor_fk = ?'. Un maillon absent ne rend aucune ligne (une ligne
        orpheline n'appartient à personne). Retourne None si 'entity' n'est pas
        en propriété transitive."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        frag = sql.cat(sql.ident(chaine["actor_fk"]), sql.kw(" = "), actor_frag)
        for h in reversed(chaine["hops"]):
            frag = sql.cat(sql.ident(h["ref"]), sql.kw(" IN (SELECT id FROM "),
                           sql.ident(h["table"]), sql.kw(" WHERE "), frag,
                           sql.kw(")"))
        return sql.cat(sql.kw(" WHERE "), frag)

    def _chain_owner_scalar(self, entity, first_hop):
        """Sous-requête scalaire (objet sql.Sql) qui rend l'id de COMPTE du
        propriétaire d'un enregistrement, à partir de l'id du PREMIER maillon.
        'first_hop' est ce PREMIER maillon sous forme de fragment sql.Sql — soit
        une valeur liée (sql.bind, cas des routes qui reçoivent la clé étrangère
        du client), soit une sous-requête (cas de _chain_owner_from_row). Dans
        tous les cas, aucune valeur ne traverse le texte SQL.

        Grimpe la chaîne maillon par maillon : la colonne de clé étrangère du
        niveau courant désigne le maillon suivant, et la dernière sélection
        'actor_fk' rend le compte. Tout maillon absent rend NULL donc
        « appartient à personne ». None si 'entity' n'est pas transitive."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        hops = chaine["hops"]
        expr = sql.cat(sql.kw("("), first_hop, sql.kw(")"))
        for i in range(1, len(hops)):
            h = hops[i]
            prev = hops[i - 1]
            expr = sql.cat(sql.kw('(SELECT '), sql.ident(h["ref"]),
                           sql.kw(' FROM '), sql.ident(prev["table"]),
                           sql.kw(' WHERE id = '), expr, sql.kw(')'))
        dernier = hops[-1]
        return sql.cat(sql.kw('(SELECT '), sql.ident(chaine["actor_fk"]),
                       sql.kw(' FROM '), sql.ident(dernier["table"]),
                       sql.kw(' WHERE id = '), expr, sql.kw(')'))

    def _chain_owner_from_row(self, entity, id_frag=None):
        """id de COMPTE du propriétaire d'une ligne de 'entity' (objet sql.Sql),
        sous chaîne transitive de profondeur quelconque. None si non transitive.
        'id_frag' est l'identifiant de la ligne sous forme de fragment sql.Sql
        (par défaut la valeur liée 'id', l'usage de _owner_lookup_sql)."""
        chaine = self._transitive_chain(entity)
        if not chaine:
            return None
        if id_frag is None:
            id_frag = sql.bind("id")
        ref_bas = chaine["hops"][0]["ref"]
        first_hop = sql.cat(sql.kw('(SELECT '), sql.ident(ref_bas),
                            sql.kw(' FROM '), sql.ident(entity.lower()),
                            sql.kw(' WHERE id = '), id_frag, sql.kw(')'))
        return self._chain_owner_scalar(entity, first_hop)

    def _chain_join(self, entity, alias_root="t"):
        """Séquence de JOIN qui fait remonter 'entity' jusqu'au maillon final.

        Retourne (depuis_sql, alias_dernier_maillon, acteur_fk) pour les routes
        de règlement : chaque maillon rejoint son parent par sa clé étrangère,
        et le dernier maillon 'alias_dernier_maillon' porte la colonne 'acteur_fk'
        du compte. Le montant, l'état et le propriétaire sortent ainsi de la
        MÊME lecture — l'invariant du point 87. Ne porte aucune valeur client,
        rien que des identifiants et des alias internes."""
        chaine = self._transitive_chain(entity)
        # (appelé seulement quand chaine n'est pas None ; sinon erreur claire)
        depuis = sql.cat(sql.ident(entity.lower()), sql.kw(f" {alias_root}"))
        cur = alias_root
        for i, h in enumerate(chaine["hops"]):
            alias = f"m{i + 1}"
            depuis = sql.cat(depuis, sql.kw(" JOIN "), sql.ident(h["table"]),
                             sql.kw(f" {alias} ON {alias}.id = {cur}."),
                             sql.ident(h["ref"]))
            cur = alias
        return depuis.text, cur, chaine["actor_fk"]

    def _owner_lookup_sql(self, entity, owner_entity):
        """Requête qui rend l'id de COMPTE du propriétaire d'un enregistrement,
        et l'acteur auquel opposer le contrôle. Partagée par Update et Delete
        (routes.py) — deux blocs jusqu'ici identiques, qu'il aurait fallu
        corriger deux fois.

        Sous propriété transitive (brique 11), c'est une jointure sur
        l'intermédiaire ; elle renvoie la même chose qu'en propriété directe
        (un id de compte), donc la comparaison qui suit chez l'appelant est
        inchangée. Un intermédiaire absent ne rend aucune ligne : une ligne
        orpheline n'appartient à personne, et le 404 de l'appelant convient."""
        chaine = self._transitive_chain(entity)
        if chaine:
            # Briques 11 et 24 : une sous-requête scalaire remonte toute la
            # chaîne jusqu'au compte, quelle que soit sa profondeur. Elle rend
            # un id de compte (None si un maillon manque), donc la comparaison
            # chez l'appelant est inchangée par rapport à la propriété directe.
            return chaine["actor"], sql.cat(
                sql.kw("SELECT "), self._chain_owner_from_row(entity))
        return owner_entity, sql.cat(
            sql.kw("SELECT "), sql.ident(f"{owner_entity.lower()}_id"),
            sql.kw(" FROM "), sql.ident(entity.lower()),
            sql.kw(" WHERE id = "), sql.bind("id"))

    def _get_incoming_relation(self, entity):
        """Retourne la première relation entrante sur 'entity' (hasMany, hasOne,
        ou belongsTo — toutes désormais gérées, voir _compute_fk_placements),
        celle qui fournit la colonne de clé étrangère dans schema.sql, ou None
        s'il n'y en a pas. Utilisé pour peupler cette colonne à la création et
        pour le contrôle d'accès par propriété ('ownedBy')."""
        placements = self._compute_fk_placements().get(entity, [])
        if not placements:
            return None
        # CORRECTIF (bêta 3) : avec plusieurs relations entrantes, prendre la
        # première déclarée revenait à désigner le « propriétaire » au hasard
        # de l'ordre d'écriture de la spec. Les règles 'ownedBy' nomment
        # explicitement l'entité propriétaire : c'est elle qui fait foi quand
        # elle existe. À défaut, on conserve la première relation déclarée.
        owners = {v for k, v in self.ownership.items() if k.split(".", 1)[0] == entity}
        chosen = next((p for p in placements if p["owner_entity"] in owners), placements[0])
        return {"source": chosen["owner_entity"], "fk_column": chosen["fk_column"]}

    def _client_fk_columns(self, entity):
        """Colonnes de clé étrangère que le CLIENT doit fournir à la création.

        Le complément exact de `_identity_fk_columns` : tout parent que le
        jeton ne désigne pas doit être désigné par l'appelant, sans quoi la
        colonne reste NULL et le rattachement demandé disparaît (un commentaire
        sans son article, une variante sans son produit). Deux exclusions, et
        deux seulement — la colonne d'identité, peuplée depuis le JWT, et la
        cible d'un compteur, déclarée à part par `schemas.py` et la branche
        `is_reputation_fk` de `routes.py` : la répéter ici l'écrirait deux fois.

        Sur une création publique, aucune identité n'est disponible et le
        comportement historique (colonnes laissées à NULL) est conservé.

        POINT 99 : le cas « aucune colonne d'identité » n'est plus réservé aux
        entités transitives. Une entité fille d'une table MÉTIER (une variante
        et son produit) n'a pas de propriétaire déduit du jeton : toutes ses
        clés étrangères viennent donc du client.
        """
        if (entity, "Create") in self.public_actions:
            return []
        placements = self._compute_fk_placements().get(entity, [])
        if not placements:
            return []
        exclues = set(self._identity_fk_columns().get(entity, set()))
        # POINT 92 : la colonne d'une cible de compteur est celle que
        # `_decrement_fk_column` trouve pour CHAQUE règle, pas celle de la
        # première relation entrante. Avec deux relations (Post et Member),
        # `_get_incoming_relation` peut désigner Post alors que l'identité
        # peuple member_id ; l'ancienne décision excluait alors post_id de
        # l'INSERT et créait une ligne orpheline. La branche
        # `is_reputation_fk` de routes.py écrit déjà chaque cible : on l'exclut
        # ici pour qu'elle soit écrite exactement une fois.
        exclues.update(self._counter_fk_columns(entity))
        # Brique 11 (point 81) : sous propriété transitive, le parent
        # « propriétaire » est justement celui que le CLIENT doit désigner (« je
        # rattache cette ligne à CETTE commande ») -- il n'est plus déduit du
        # jeton. Il rejoint donc les autres parents (aucune colonne d'identité
        # n'existe alors), et la route Create vérifie ensuite que
        # l'enregistrement désigné appartient bien à l'appelant.
        return [p["fk_column"] for p in placements if p["fk_column"] not in exclues]

    def _identity_fk_columns(self):
        """Colonnes de clé étrangère peuplées depuis l'identité JWT de l'appelant.

        Retourne {entité: {colonnes}}. Ce sont celles que la route Create
        remplit avec 'current_user_id' (identifiant de compte), et non avec
        une valeur du corps de requête — elles référencent donc le registre
        des comptes, pas la table métier homonyme. C'est la source UNIQUE de
        cette distinction : le schéma SQL en tire son 'REFERENCES', le contrat
        son 'references_account', la route Create son 'populate_owner', la
        route de règlement la colonne qu'elle compare à l'appelant, et
        'requiresOwn' la colonne où chercher une fiche.

        POINT 99 : le parent doit être un ACTEUR. « Peuplée depuis l'identité de
        l'appelant » n'a de sens que si le parent EST un compte : une entité
        fille d'une table métier (une variante et son produit) n'a pas de
        propriétaire à déduire du jeton. Sans cette condition, une telle colonne
        recevait `current_user_id` et se déclarait `REFERENCES _monl_users` — la
        variante était rattachée au vendeur qui l'avait créée, jamais à son
        produit, et le client ne pouvait désigner aucun parent. Le nom de la
        colonne disait une chose, son contenu une autre : le défaut du point 80,
        par l'autre bout du même mécanisme.

        Le choix ne dépend PAS de l'ordre de déclaration des relations : seuls
        les parents acteurs sont candidats, et la règle 'ownedBy' tranche entre
        eux s'il y en a plusieurs.
        """
        route_map = self._compute_route_map()
        creatable = {plan.base_target for (act, _k), plan in route_map.items()
                     if act == "Create"}
        identity_cols = {}
        for entity in self.entities:
            if entity not in creatable:
                continue
            if (entity, "Create") in self.public_actions:
                continue  # aucune identité fiable : la colonne reste NULL
            if entity in self.transitive_ownership:
                # Brique 11 : la colonne contient un id d'enregistrement
                # intermédiaire, pas un id de compte -- elle référence donc la
                # vraie table métier, et non '_monl_users'.
                continue
            cibles_compteur = {r["target_entity"]
                               for r in self.reputation_rules_by_trigger.get(entity, [])}
            candidats = [p for p in self._compute_fk_placements().get(entity, [])
                         if p["owner_entity"] in self.actors
                         # cible choisie par le client : vraie référence métier
                         and p["owner_entity"] not in cibles_compteur]
            if not candidats:
                continue
            proprietaires = {v for k, v in self.ownership.items()
                             if k.split(".", 1)[0] == entity}
            choisi = next((p for p in candidats if p["owner_entity"] in proprietaires),
                          candidats[0])
            identity_cols.setdefault(entity, set()).add(choisi["fk_column"])
        return identity_cols
