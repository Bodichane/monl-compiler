"""Le verrou de l'enregistrement payé (point 91).

`_payment_locked_parents` a UNE source, partagée par les cinq routes qu'il
ferme ET par le contrat (`_verrou_paiement` l'appelle, il ne recalcule
pas la chaîne — deux vérités finiraient par diverger)."""

from string import Template

from ..ir import PAYMENT_STATUS_COLUMN


class PaiementMixin:
    """Le verrou de l'enregistrement payé (point 91)."""

    def _payment_lock_field(self, entity):
        """Champ 'payable' de 'entity', ou None. Un enregistrement encaissé ne
        se modifie plus : c'est ce que verrouille la brique 18 (point 91)."""
        return self.payable_by_entity.get(entity)

    def _payment_locked_parents(self, source_entity):
        """Parents PAYABLES dont une écriture sur 'source_entity' changerait le
        montant. Source unique du verrou, partagée par Create, Update et Delete.

        C'est le pendant de `_aggregation_recomputes` : partout où une écriture
        sur l'enfant RECALCULE le total d'un parent, ce total peut déjà avoir
        été encaissé. Verrouiller le seul parent ne suffisait pas — le trou se
        prenait par la ligne : 89 € réglés, puis une paire à 149 € ajoutée à la
        même commande, et le serveur affichait 238 € toujours marqués 'payee'
        (vérifié contre un vrai serveur avant d'écrire ce code).

        Retourne la colonne de clé étrangère qui désigne le parent, son entité
        et sa table. Un parent non payable ne verrouille rien : un panier de
        pièces détachées reste modifiable, c'est l'encaissement qui fige."""
        verrous = []
        vus = set()
        for plan in self.aggregations_by_source.get(source_entity, ()):
            parent = plan.entity
            if parent not in self.payable_by_entity or parent in vus:
                continue
            fk = plan.parent_fk
            vus.add(parent)
            verrous.append({"fk_column": fk, "entity": parent,
                            "table": parent.lower()})
        return verrous

    def _payment_lock_lines(self, table, id_expr, entity, indent="    ",
                            var="_regle"):
        """Lignes de garde : refuse l'écriture si l'enregistrement visé est
        encaissé. 409 et non 403 — ce n'est pas un droit qui manque, c'est un
        état définitif, et le message dit lequel."""
        return [
            Template(r"""${indent}cursor.execute('SELECT "${PAYMENT_STATUS_COLUMN}" FROM "${table}" WHERE id = ?', (${id_expr},))""").substitute(indent=indent, PAYMENT_STATUS_COLUMN=PAYMENT_STATUS_COLUMN, table=table, id_expr=id_expr),
            Template(r"""${indent}${var} = cursor.fetchone()""").substitute(indent=indent, var=var),
            Template(r"""${indent}if ${var} and ${var_2}[0] == 'payee':""").substitute(indent=indent, var=var, var_2=var),
            Template(r"""${indent}    conn.close()""").substitute(indent=indent),
            Template(r"""${indent}    raise HTTPException(status_code=409, detail=(""").substitute(indent=indent),
            Template(r"""${indent}        '${entity} déjà réglé : un enregistrement encaissé ne peut plus être '""").substitute(indent=indent, entity=entity),
            Template(r"""${indent}        'modifié ni supprimé. Passez par un remboursement chez le prestataire.'))""").substitute(indent=indent),
        ]
