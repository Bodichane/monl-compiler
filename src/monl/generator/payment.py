"""The lock on a paid record (point 91).

`_payment_locked_parents` has ONE source, shared by the five routes it
closes AND by the contract (`_verrou_paiement` calls it, it does not
recompute the chain — two truths would eventually diverge)."""

from string import Template

from ..ir import PAYMENT_STATUS_COLUMN


class PaiementMixin:
    """The lock on a paid record (point 91)."""

    def _payment_lock_field(self, entity):
        """The 'payable' field of 'entity', or None. A charged record can no longer
        be changed: that is what brick 18 locks (point 91)."""
        return self.payable_by_entity.get(entity)

    def _payment_locked_parents(self, source_entity):
        """PAYABLE parents whose amount a write on 'source_entity' would change.
        Single source of the lock, shared by Create, Update and Delete.

        It is the counterpart of `_aggregation_recomputes`: wherever a write on the
        child RECOMPUTES a parent's total, that total may already have been
        charged. Locking the parent alone was not enough — the hole was reached
        through the line: €89 paid, then a €149 pair added to the same order, and
        the server showed €238 still marked 'payee' (checked against a real server
        before writing this code).

        Returns the foreign key column that designates the parent, its entity and
        its table. A non-payable parent locks nothing: a cart of spare parts stays
        editable, it is the charge that freezes."""
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
        """Guard lines: refuse the write if the targeted record has been charged.
        409 and not 403 — no permission is missing, it is a final state, and the
        message says which one."""
        return [
            Template(r"""${indent}cursor.execute('SELECT "${PAYMENT_STATUS_COLUMN}" FROM "${table}" WHERE id = ?', (${id_expr},))""").substitute(indent=indent, PAYMENT_STATUS_COLUMN=PAYMENT_STATUS_COLUMN, table=table, id_expr=id_expr),
            Template(r"""${indent}${var} = cursor.fetchone()""").substitute(indent=indent, var=var),
            Template(r"""${indent}if ${var} and ${var_2}[0] == 'payee':""").substitute(indent=indent, var=var, var_2=var),
            Template(r"""${indent}    conn.close()""").substitute(indent=indent),
            Template(r"""${indent}    raise HTTPException(status_code=409, detail=(""").substitute(indent=indent),
            Template(r"""${indent}        '${entity} already paid: a charged record can no longer be '""").substitute(indent=indent, entity=entity),
            Template(r"""${indent}        'modified or deleted. Go through a refund with the provider.'))""").substitute(indent=indent),
        ]
